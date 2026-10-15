"""Orchestrateur de conversation : routage → (niveau 0 | boucle d'outils LLM) → réponse tracée.

Trois contacts (directeur sportif, directeur technique, entraîneur adjoint) : chacun a son script de
rôle, l'identité de la personne en poste dans la sauvegarde et son fil de messages par carrière.
Les réponses peuvent être diffusées au fil de l'écriture (`on_event`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, func, insert, select

from clubdirector.ai.club_brief import build_club_dossier
from clubdirector.ai.director_identity import STAFF_ROLES, find_staff
from clubdirector.ai.persona import (
    ROLE_LABELS,
    TAKE_OFFICE_REQUEST,
    build_context_message,
    build_system_prompt,
    first_contact_request,
)
from clubdirector.ai.prefetch import prefetch_brief, prefetch_calls
from clubdirector.ai.providers.base import IAIProvider, ProviderError
from clubdirector.ai.router import answer_intent, classify, intent_allowed, wants_premium
from clubdirector.ai.topics import (
    OFF_TOPIC_HINT,
    OFF_TOPIC_RE,
    facts_hint,
    people_facts,
    redirect_hint,
    topic_owner,
    unknown_hint,
    unknown_people,
)
from clubdirector.database import schema as s
from clubdirector.memory.decisions import capture_decisions, decisions_hint
from clubdirector.memory.store import ConversationStore, MemoryStore
from clubdirector.memory.summaries import summarize, summary_block
from clubdirector.sync.season import season_label
from clubdirector.tools.registry import ToolContext, ToolRegistry, ToolResult
from clubdirector.transfers.dossiers import DOSSIER_TOOLS, DossierStore
from clubdirector.transfers.operations import operation_brief, operation_request

log = logging.getLogger(__name__)
MAX_TOOL_RESULT_CHARS = 12000
CONTACT_ROLES: tuple[str, ...] = tuple(STAFF_ROLES)
DIRECTOR = "directeur_sportif"
# Réflexion préalable du modèle : seulement quand l'entraîneur demande une vraie analyse.
DEEP_RE = re.compile(
    r"r[ée]fl[ée]chi|en profondeur|analyse (approfondie|d[ée]taill[ée]e|compl[èe]te)|plan complet|"
    r"rapport complet|point complet|[ée]tude compl[èe]te|plan de mercato|strat[ée]gie (compl[èe]te|globale)",
    re.IGNORECASE,
)
# Message de conversation courante (salut, ça va, merci…) : une seule bulle, tout de suite.
# Reconnu quand presque tous ses mots sont des mots de politesse (au plus deux autres : un prénom…).
SMALL_TALK_WORDS = frozenset("""
salut bonjour bonsoir coucou hello hey yo wesh re ça ca va vas allez comment et toi vous tu bien merci beaucoup
mille bonne bon journée journee soirée soiree nuit week-end weekend chance à a plus demain bientôt bientot au revoir
ciao ok okay d'accord dac reçu recu bien parfait top super génial genial bravo bienvenue coach chef boss mister
le la les mon ma cher chère ami oui non
""".split())
def _words(text: str) -> list[str]:
    return re.findall(r"[\w'-]+", text.lower().replace("’", "'"))


def is_small_talk(text: str) -> bool:
    words = _words(text)
    if not words or len(words) > 8:
        return False
    known = sum(1 for w in words if w in SMALL_TALK_WORDS)
    return known >= 1 and len(words) - known <= 2 and known >= len(words) / 2


# Types de messages de l'entraîneur : chacun appelle une façon de répondre différente.
REQUEST_RE = re.compile(
    r"(?:^|[:;,.!?]\s*|\bet\s+)\W*(?:(?:est-ce que )?(?:tu peux|tu pourrais|peux-tu|pourrais-tu|vous pouvez|vous pourriez|"
    r"pouvez-vous|pourriez-vous|j'aimerais(?: que)?|je voudrais(?: que)?|je veux(?: que)?|on veut|on voudrait|on aimerait|"
    r"on doit|il nous faut|il (?:me )?faut|il faudrait|merci de|"
    r"n'oublie pas de|essaie de|essaye de)\s+)?(?:tu |vous )?(?:me |nous |m'|lui |leur |le |la |les |l')?"
    r"(?:pr[ée]pare|trouve|cherche|faire|fais|faites|fait|analyse|compare|liste|propose|donne|montre|envoie|"
    r"vends|vend|ach[èe]te|recrute|prolonge|n[ée]gocie|regarde|v[ée]rifie|calcule|chiffre|estime|[ée]tudie|"
    r"identifie|rep[èe]re|sors|r[ée]dige|organise|planifie|garde|retiens|note|m[ée]morise|oublie|pr[ée]vois|"
    r"construis|classe|r[ée]sume|explique|d[ée]taille|[ée]value|[ée]tablis|dresse|sugg[èe]re|conseille|"
    r"aide|occupe|pr[ée]pare|lance|bloque|vire|lib[èe]re|pr[êe]te|mets|place|ajoute|enl[èe]ve|retire)",
    re.IGNORECASE,
)
QUESTION_RE = re.compile(
    r"^\W*(qui|que|qu'|quoi|quel|quelle|quels|quelles|combien|comment|pourquoi|quand|o[ùu]|est-ce|lequel|"
    r"laquelle|lesquels|on en est|t'en penses|tu en penses|vous en pensez|c'est quoi|y a-t-il|il y a)\b",
    re.IGNORECASE,
)
REPLY_START = frozenset("""oui non ouais ok okay d'accord dac vas-y allez-y go fonce on banco carrément carrement
plutôt plutot pas jamais surtout laisse laissez attends attendez je j' évidemment evidemment bien sûr sur exactement
voilà voila parfait top nickel ça ca les le la lui eux aucun aucune tous toutes""".split())
KIND_HINTS = {
    "politesse": ("[Consigne automatique — type de message : DISCUSSION (politesse). Réponds en UNE seule bulle d'une "
                  "ou deux phrases, tout de suite, sans consulter de données et sans proposer d'action. Réagis exactement "
                  "à ce que dit l'entraîneur : un merci appelle « avec plaisir », un au revoir appelle un au revoir, un "
                  "« ça va ? » appelle une réponse ; ne dis « bonjour » que s'il vient de te saluer.]"),
    "discussion": ("[Consigne automatique — type de message : DISCUSSION. L'entraîneur partage un avis ou une "
                   "information : réagis naturellement en une ou deux bulles, comme un collègue (accord, nuance, "
                   "conséquence pour ton domaine). Pas de rapport, pas de liste.]"),
    "question": ("[Consigne automatique — type de message : QUESTION. Donne la réponse d'abord, directement, en une "
                 "ou deux bulles avec les chiffres utiles. Si le chiffre demandé n'est pas dans le dossier, consulte "
                 "les données AVANT de répondre ; n'estime jamais un chiffre. Pas de développement non demandé.]"),
    "demande": ("[Consigne automatique — type de message : DEMANDE. Fais le travail maintenant : consulte les données "
                "nécessaires (toutes les consultations d'un coup, dans le même tour, pas l'une après l'autre) puis "
                "livre un résultat concret (noms, chiffres, recommandation) en bulles aérées. Si "
                "une action dans FM26 est nécessaire, prépare-la et dis précisément ce que l'entraîneur doit faire "
                "dans le jeu.]"),
    "accord": ("[Consigne automatique — type de message : RÉPONSE (accord) à ta proposition. L'entraîneur accepte : fais "
               "MAINTENANT ce que tu proposais (consulte les données nécessaires) et livre le résultat concret dans ce "
               "message. Interdit : « je m'en occupe », « je reviens vers vous », « je lance ça ».]"),
    "reponse": ("[Consigne automatique — type de message : RÉPONSE de l'entraîneur à ta dernière question. Prends-la "
                "en compte : si c'est un accord sur ce que tu proposais, fais-le maintenant ; si c'est une décision "
                "durable, retiens-la ; sinon accuse réception en une bulle et enchaîne sur la suite logique.]"),
}


AGREE_RE = re.compile(r"^\W*(oui|ouais|ok|okay|d'accord|dac|vas-y|allez-y|go|banco|lance|fonce|parfait|top|"
                      r"carr[ée]ment|bien s[uû]r|[ée]videmment|volontiers|fais[- ]le|faites[- ]le)\b", re.IGNORECASE)


def message_kind(text: str, previous: str | None = None) -> str:
    """politesse | discussion | question | demande | reponse — `previous` : dernier message du contact.

    - réponse : le contact venait de poser une question et l'entraîneur y répond (sans en poser une) ;
    - politesse : salut, ça va, merci… ;
    - demande : un travail à faire (prépare, trouve, vends, analyse…) ;
    - question : une information à donner ;
    - discussion : un avis, une information partagée."""
    words = _words(text)
    if not words:
        return "politesse"
    last_bubble = (previous or "").strip().split("\n\n")[-1]
    request = bool(REQUEST_RE.search(text))
    if "?" in last_bubble and "?" not in text and len(words) <= 25 and (words[0] in REPLY_START or not request):
        return "reponse"
    if is_small_talk(text):
        return "politesse"
    if request:
        return "demande"
    if "?" in text or QUESTION_RE.search(text):
        return "question"
    return "discussion"


# Demande de composition : le onze est calculé par l'outil (notes de poste FM26) AVANT d'appeler le
# modèle, qui le présente et le commente. Il ne le devine jamais.
LINEUP_RE = re.compile(
    r"\b(onze|11 de d[ée]part|compo(sition)?s?|[ée]quipe[- ]type|aligne(r|rais|rait|s|z)?|titulaires?|line-?up|"
    r"qui (je )?(fais|mets|met) jouer|qui (doit|va|devrait) jouer|qui tu (mets|ferais jouer)|qui joue(nt)?)\b",
    re.IGNORECASE,
)
SYSTEM_RE = re.compile(r"\b([345])[- ]?([1-5])[- ]?([1-5])(?:[- ]?([1-3]))?\b")
ROTATION_RE = re.compile(r"\b(rotation|tourner|tourne|m[ée]nager|m[ée]nage|reposer|repos|fra[iî]cheur|frais)\b", re.IGNORECASE)
ABSENT_RE = re.compile(r"\bsans\s+([^.?!;:\n]+)", re.IGNORECASE)


FOLLOW_UP_RE = re.compile(r"^\W*(et )?(sans|avec|en|si)\b", re.IGNORECASE)
LINEUP_SHOWN_RE = re.compile(r"\b[345]-[1-5]-[1-5](-[1-3])?\b|\bonze\b", re.IGNORECASE)


def lineup_request(text: str, previous: str | None = None) -> dict | None:
    """Arguments de `propose_lineup` si le message demande une composition, sinon None.

    `previous` : dernier message du contact ; « Et sans Dybala ? » juste après un onze est une
    nouvelle demande de composition."""
    follow_up = bool(previous and LINEUP_SHOWN_RE.search(previous) and FOLLOW_UP_RE.search(text))
    if not LINEUP_RE.search(text) and not SYSTEM_RE.search(text) and not follow_up:  # « et en 4-3-3 ? » : un système suffit
        return None
    from clubdirector.tools.lineup import SYSTEMS

    args: dict = {}
    m = SYSTEM_RE.search(text)
    if m:
        system = "-".join(g for g in m.groups() if g)
        if system in SYSTEMS:
            args["systeme"] = system
    if ROTATION_RE.search(text):
        args["rotation"] = True
    absents = []
    for chunk in ABSENT_RE.findall(text):
        for name in re.split(r",|\bet\b|\bni\b", chunk):
            name = name.strip(" '\"")
            if name and len(name) <= 40 and name[:1].isupper():
                absents.append(name)
    if absents:
        args["absents"] = absents
    return args


def lineup_brief(data: dict) -> str:
    onze = " ; ".join(f"{x['poste']} {x['joueur']} ({x['note_poste']}/20)" for x in data["onze"])
    bench = ", ".join(x["joueur"] for x in data.get("banc", []))
    out = (f"[Composition calculée par l'outil propose_lineup sur les notes de poste FM26, système {data['systeme']} — "
           f"base OBLIGATOIRE de ta réponse : {onze}. Remplaçants : {bench}.")
    if data.get("exclus"):
        out += " Écartés : " + ", ".join(f"{x['joueur']} ({x['raison']})" for x in data["exclus"]) + "."
    if data.get("alertes"):
        out += " Alertes : " + " ".join(data["alertes"])
    return out + (" Présente ce onze ligne par ligne avec ton avis de terrain ; si tu proposes un changement, uniquement "
                  "un joueur noté ≥ 15 au même poste. Blessés et suspendus du jour sont déjà écartés (état de la dernière "
                  "sauvegarde) ; cite les écartés s'il y en a.]")


TOOL_LABELS = {
    "get_club_squad": "effectif", "get_player_profile": "fiche joueur", "get_player_contract": "contrat",
    "get_player_attributes": "attributs", "get_player_statistics": "statistiques", "get_player_season_history": "historique",
    "get_recent_matches": "derniers matchs", "get_match_details": "détails du match", "get_upcoming_matches": "calendrier",
    "get_league_table": "classement", "get_club_finances": "finances", "get_transfer_budget": "budget transferts",
    "get_wage_budget": "masse salariale", "get_active_tactics": "tactique", "get_injured_players": "blessés",
    "get_transfer_history": "transferts", "search_players": "recherche de joueurs", "compare_players": "comparaison",
    "search_expiring_contracts": "fins de contrat", "get_top_players_stat": "classement statistique",
    "get_alerts": "alertes", "analyze_squad": "analyse d'effectif", "identify_weak_positions": "postes faibles",
    "analyze_tactical_fit": "adéquation tactique", "find_recruitment_targets": "cibles de recrutement",
    "estimate_wage_affordability": "marge salariale", "analyze_contract_risks": "risques contractuels",
    "evaluate_youth_prospects": "jeunes", "remember": "mémoire", "list_memories": "mémoire", "forget": "mémoire",
    "describe_game_tables": "données du jeu", "query_game_table": "données du jeu",
    "get_club_league_history": "palmarès", "get_club_staff": "staff", "get_current_save": "sauvegarde",
    "get_managed_club": "club", "propose_lineup": "composition", "list_dossiers": "dossiers",
    "generate_scout_report": "rapport de recrutement", "plan_transfer_window": "plan de mercato",
    "analyze_player_performance": "performances",
}
Event = Callable[[dict], None]

# Outils de chaque contact : chacun reste dans son métier (None = tous les outils).
COMMON_TOOLS = {"get_current_save", "get_managed_club", "describe_game_tables", "query_game_table",
                "remember", "list_memories", "forget"}
ROLE_TOOLS: dict[str, set[str] | None] = {
    "directeur_sportif": None,
    # Le staff technique, pas les joueurs.
    "directeur_technique": COMMON_TOOLS | {"get_club_staff", "get_club_league_history", "get_club_finances",
                                           "get_wage_budget", "get_active_tactics", "get_tactical_instructions"},
    # Le terrain : matchs, statistiques, joueurs, entraînement, composition, notes.
    "entraineur_adjoint": COMMON_TOOLS | {
        "get_club_squad", "get_player_profile", "get_player_attributes", "get_player_statistics",
        "get_player_season_history", "get_recent_matches", "get_match_details", "get_upcoming_matches",
        "get_league_table", "get_active_tactics", "get_tactical_instructions", "get_injured_players",
        "compare_players", "get_top_players_stat", "get_alerts", "analyze_squad", "identify_weak_positions",
        "analyze_tactical_fit", "analyze_player_performance", "evaluate_youth_prospects", "propose_lineup",
    },
}


@dataclass
class ChatAnswer:
    text: str
    route: str  # niveau0 | niveau1 | niveau2 | niveau3 | indisponible
    conversation_id: int
    tools: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provider: str | None = None
    cost_usd: float = 0.0
    message_id: int | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _compact(data: str) -> str:
    if len(data) <= MAX_TOOL_RESULT_CHARS:
        return data
    return data[:MAX_TOOL_RESULT_CHARS] + '…"[tronqué : affinez la requête (filtres, limit)]"'


def _alternate(messages: list[dict]) -> list[dict]:
    """Fusionne les messages consécutifs d'un même rôle (le modèle attend une alternance stricte)."""
    out: list[dict] = []
    for m in messages:
        if out and out[-1]["role"] == m["role"]:
            out[-1] = {"role": m["role"], "content": out[-1]["content"] + "\n\n" + m["content"]}
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


def tool_label(name: str) -> str:
    return TOOL_LABELS.get(name, "données du jeu")


class Orchestrator:
    def __init__(self, engine: Engine, registry: ToolRegistry, providers: list[IAIProvider], *,
                 mode: str = "local", monthly_budget_usd: float = 0.0, max_tool_rounds: int = 6,
                 history_messages: int = 12, prefs_store: Any = None, thinking: str = "auto") -> None:
        self.engine = engine
        self.prefs_store = prefs_store
        self.registry = registry
        self.providers = sorted(providers, key=lambda p: p.tier)
        self.mode = mode
        self.monthly_budget_usd = monthly_budget_usd
        self.max_tool_rounds = max_tool_rounds
        self.history_messages = history_messages
        self.thinking = thinking  # auto | on | off
        self.conversations = ConversationStore(engine)
        self._active = 0
        self._active_lock = threading.Lock()
        self._intro_lock = threading.Lock()
        self._intros: set[int] = set()
        self._warmed: dict[str, str] = {}  # rôle -> empreinte du prompt déjà calculé par le serveur local

    # ------------------------------------------------------------------ budget
    def month_spend(self) -> float:
        start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        with self.engine.connect() as c:
            return float(c.execute(select(func.coalesce(func.sum(s.ai_usage.c.cost_usd), 0.0))
                                   .where(s.ai_usage.c.created_at >= start)).scalar_one())

    def _record_usage(self, p: IAIProvider, model: str | None, tin: int, tout: int) -> float:
        cost = tin / 1e6 * p.input_cost_per_mtok + tout / 1e6 * p.output_cost_per_mtok
        with self.engine.begin() as c:
            c.execute(insert(s.ai_usage).values(provider=p.name, model=model or p.model, tier=p.tier,
                                                input_tokens=tin, output_tokens=tout, cost_usd=cost,
                                                created_at=datetime.now(UTC)))
        return cost

    def choose_provider(self, question: str, force_tier: int | None = None) -> IAIProvider | None:
        if not self.providers:
            return None
        allowed = {"local": {1}, "hybride": {1, 2}, "premium": {1, 2, 3}}.get(self.mode, {1})
        if force_tier is not None:
            wanted = force_tier
        elif wants_premium(question) and 3 in allowed:
            wanted = 3
        else:
            wanted = min(allowed)
        candidates = [p for p in self.providers if p.tier == wanted and p.tier in allowed]
        if not candidates:
            candidates = [p for p in self.providers if p.tier in allowed]
        if not candidates:
            return None
        p = candidates[0]
        paid = p.input_cost_per_mtok > 0 or p.output_cost_per_mtok > 0
        if paid and self.monthly_budget_usd > 0 and self.month_spend() >= self.monthly_budget_usd:
            free = [x for x in self.providers if x.input_cost_per_mtok == 0 and x.output_cost_per_mtok == 0]
            return free[0] if free else None
        return p

    def _wants_thinking(self, question: str) -> bool:
        if self.thinking == "on":
            return True
        if self.thinking == "off":
            return False
        return bool(DEEP_RE.search(question))

    # ------------------------------------------------------------------ staff (contacts)
    def staff(self, tctx: ToolContext, role: str):
        """La personne en poste pour `role` dans la carrière (sauvegarde), ou None (poste vacant)."""
        override = tctx.prefs.staff_overrides.get(role)
        if role == DIRECTOR and override is None:
            override = tctx.prefs.director_staff_uid
        return find_staff(self.engine, tctx.ctx.career_id, tctx.ctx.club_uid, role, override)

    def team(self, tctx: ToolContext) -> dict[str, Any]:
        return {role: self.staff(tctx, role) for role in CONTACT_ROLES}

    def director(self, tctx: ToolContext):
        """Directeur sportif en poste dans la carrière (sauvegarde), ou None."""
        return self.staff(tctx, DIRECTOR)

    def thread(self, tctx: ToolContext, role: str, member=None) -> int:
        member = member if member is not None else self.staff(tctx, role)
        title = f"{ROLE_LABELS[role]} — {member.name if member else 'poste vacant'}"
        return self.conversations.thread(tctx.ctx.career_id, role, member.uid if member else 0, title)

    def intro_pending(self, tctx: ToolContext, role: str, member=None) -> bool:
        """Vrai si ce contact n'a encore jamais écrit à l'entraîneur (nouveau titulaire compris)."""
        member = member if member is not None else self.staff(tctx, role)
        conv = self.conversations.find_thread(tctx.ctx.career_id, role, member.uid if member else 0)
        return conv is None or self.conversations.count(conv) == 0

    def office_pending(self, tctx: ToolContext, director=None) -> bool:
        """Vrai si le directeur en poste n'a pas encore fait sa prise de poste (nouvelle carrière ou nouveau directeur)."""
        director = director if director is not None else self.director(tctx)
        uid = director.uid if director else 0
        return tctx.prefs.office_by_career.get(str(tctx.ctx.career_id)) != uid

    def _mark_office_taken(self, tctx: ToolContext, director) -> None:
        uid = director.uid if director else 0
        key = str(tctx.ctx.career_id)
        tctx.prefs.office_by_career[key] = uid
        if tctx.ctx.career_id not in tctx.prefs.office_taken:
            tctx.prefs.office_taken.append(tctx.ctx.career_id)
        if self.prefs_store is not None:
            prefs = self.prefs_store.load()
            prefs.office_by_career[key] = uid
            if tctx.ctx.career_id not in prefs.office_taken:
                prefs.office_taken.append(tctx.ctx.career_id)
            self.prefs_store.save(prefs)

    # ------------------------------------------------------------------ conversation
    def take_office(self, tctx: ToolContext) -> ChatAnswer:
        """Prise de poste explicite du directeur sportif dans la carrière active."""
        conv = self.conversations.create(tctx.ctx.career_id, "Prise de poste")
        return self.ask(tctx, TAKE_OFFICE_REQUEST, conversation_id=conv, force_tier=1, taking_office=True)

    def send(self, tctx: ToolContext, role: str, text: str, on_event: Event | None = None) -> ChatAnswer:
        """Message de l'entraîneur à un contact du téléphone."""
        member = self.staff(tctx, role)
        conv = self.thread(tctx, role, member)
        return self.ask(tctx, text, conversation_id=conv, role=role, member=member, on_event=on_event)

    def introduce(self, tctx: ToolContext, role: str, on_event: Event | None = None) -> ChatAnswer | None:
        """Premier message du contact (prise de poste pour un nouveau directeur sportif).

        None si le contact a déjà écrit, ou si son premier message est déjà en cours d'écriture."""
        member = self.staff(tctx, role)
        conv = self.thread(tctx, role, member)
        with self._intro_lock:
            if conv in self._intros or self.conversations.count(conv) > 0:
                return None
            self._intros.add(conv)
        try:
            taking_office = role == DIRECTOR and self.office_pending(tctx, member)
            return self.ask(tctx, first_contact_request(role, taking_office=taking_office), conversation_id=conv,
                            role=role, member=member, on_event=on_event, taking_office=taking_office,
                            hidden_question=True, force_tier=1)
        finally:
            with self._intro_lock:
                self._intros.discard(conv)

    def notify(self, tctx: ToolContext, role: str, instruction: str, fallback: str,
               on_event: Event | None = None) -> ChatAnswer | None:
        """Message que le contact écrit DE LUI-MÊME (faits nouveaux après une sauvegarde).

        `instruction` (cachée) donne les faits au modèle, qui rédige ; sans modèle, `fallback` (les faits
        eux-mêmes) est écrit tel quel. Un contact qui n'a jamais écrit se présente d'abord. None : poste vacant."""
        member = self.staff(tctx, role)
        if member is None and role != DIRECTOR:
            return None
        conv = self.thread(tctx, role, member)
        if self.conversations.count(conv) == 0:
            self.introduce(tctx, role)
        answer = self.ask(tctx, instruction, conversation_id=conv, role=role, member=member, on_event=on_event,
                          hidden_question=True, force_tier=1)
        if answer.route == "indisponible" or answer.message_id is None:
            mid = self.conversations.add_message(conv, "assistant", fallback, game_date=tctx.ctx.game_date, route="niveau0")
            answer = ChatAnswer(fallback, "niveau0", conv, answer.tools, answer.limitations, message_id=mid)
        return answer

    def summarize_threads(self, tctx: ToolContext, roles: tuple[str, ...] = CONTACT_ROLES) -> list[str]:
        """Résume la partie ancienne des fils (hors fenêtre d'historique) sur le modèle local. Rôles résumés."""
        provider = self.choose_provider("", 1)
        if provider is None:
            return []
        done = []
        for role in roles:
            if self._active:
                break  # une vraie conversation passe avant
            member = self.staff(tctx, role)
            conv = self.conversations.find_thread(tctx.ctx.career_id, role, member.uid if member else 0)
            if conv is None:
                continue
            label = f"{ROLE_LABELS[role]} ({member.name})" if member else ROLE_LABELS[role]
            try:
                if summarize(self.engine, provider, conv, label, self.history_messages):
                    done.append(role)
            except ProviderError as exc:
                log.info("Résumé interrompu : %s", exc)
                break
        return done

    def _capture_decisions(self, tctx: ToolContext, question: str) -> list:
        """Décisions durables de l'entraîneur (« on ne vend pas Soulé ») retenues pour tout le staff."""
        try:
            squad = tctx.repo.squad(tctx.ctx, team_slot=None)
            return capture_decisions(self.engine, tctx.ctx.career_id, question, squad, tctx.ctx.game_date)
        except Exception:  # noqa: BLE001 — la mémoire ne bloque jamais une réponse
            log.exception("Capture des décisions en échec")
            return []

    def _operation(self, tctx: ToolContext, question: str) -> tuple[str, dict] | None:
        """Outil de préparation (et arguments) d'une opération demandée au directeur sportif, ou None."""
        try:
            op = operation_request(tctx, question)
        except Exception:  # noqa: BLE001 — la détection ne bloque jamais une réponse
            log.exception("Détection d'opération en échec")
            return None
        return (op[0], op[1]) if op else None

    def _open_dossier(self, tctx: ToolContext, tool: str, args: dict, result: ToolResult, role: str, conv: int) -> None:
        """Une préparation (achat, vente, contre-offre, contrat) devient un dossier suivi dans les sauvegardes."""
        try:
            DossierStore(self.engine).open_from_tool(tctx, tool, args, result.data, role=role, conversation_id=conv)
        except Exception:  # noqa: BLE001 — le suivi ne bloque jamais une réponse
            log.exception("Ouverture de dossier en échec")

    def ask(self, tctx: ToolContext, question: str, *, conversation_id: int | None = None,
            force_tier: int | None = None, taking_office: bool | None = None, role: str = DIRECTOR,
            member: Any = None, on_event: Event | None = None, hidden_question: bool = False) -> ChatAnswer:
        conv = conversation_id or self.conversations.create(tctx.ctx.career_id, question[:80])
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in self.conversations.messages(conv, limit=self.history_messages)
            if m["role"] in ("user", "assistant")
        ]
        notes: list[str] = []
        if not hidden_question:
            self.conversations.add_message(conv, "user", question, game_date=tctx.ctx.game_date)
            saved = self._capture_decisions(tctx, question)
            if saved:
                notes.append(decisions_hint(saved))
        trace: list[dict] = []

        def run(tool: str, args: dict):
            r = self.registry.execute(tool, args, tctx)
            trace.append({"tool": tool, "args": args, "ok": r.ok, "error": r.error})
            return r

        answer: ChatAnswer
        intent = classify(question) if force_tier is None and not hidden_question else None
        if not intent_allowed(role, intent):  # chaque contact ne répond sans IA que dans son métier
            intent = None
        previous = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), None)
        if intent is not None and message_kind(question, previous) != "question":
            intent = None  # « le groupe a bien réagi après le dernier match » est une discussion, pas une question
        if intent is not None:
            try:
                text, lim = answer_intent(intent, run, lambda names: tctx.repo.club_short_names(tctx.ctx, names))
                answer = ChatAnswer(text, "niveau0", conv, trace, sorted(set(lim)))
            except LookupError as exc:
                answer = ChatAnswer(f"Donnée non disponible : {exc}", "niveau0", conv, trace)
            if on_event:
                on_event({"type": "delta", "text": answer.text})
        else:
            if member is None:
                member = self.staff(tctx, role)
            # La prise de poste est le premier message du directeur (`introduce`, ou `take_office`) :
            # elle ne détourne jamais une question de l'entraîneur.
            office = bool(taking_office) and role == DIRECTOR
            answer = self._llm(tctx, question, history, conv, trace, force_tier, office, member, role, on_event, notes)
            if role == DIRECTOR and answer.route.startswith("niveau") and (office or self.office_pending(tctx, member)):
                self._mark_office_taken(tctx, member)
        if answer.route != "indisponible" or not hidden_question:
            answer.message_id = self.conversations.add_message(
                conv, "assistant", answer.text, game_date=tctx.ctx.game_date, route=answer.route, tool_trace=trace)
        return answer

    def _prompt(self, tctx: ToolContext, role: str, member: Any, history: list[dict], question: str,
                taking_office: bool = False, conv: int | None = None,
                notes: list[str] | None = None) -> tuple[str, list[dict]]:
        ctx = tctx.ctx
        team = self.team(tctx)
        team[role] = member
        system = build_system_prompt(
            director_name=tctx.prefs.director_name, club=ctx.club_name, persona=tctx.prefs.persona,
            knowledge=tctx.prefs.knowledge_mode, manager=ctx.manager_name, identity=member, role=role, team=team)
        context = build_context_message(
            club=ctx.club_name, game_date=ctx.game_date.isoformat() if ctx.game_date else None,
            season=season_label(ctx.season_start_year), dossier=build_club_dossier(self.registry, tctx, role),
            memories=MemoryStore(self.engine).list(ctx.career_id)) + summary_block(self.engine, conv)
        if taking_office and role == DIRECTOR and not question.startswith("[Message automatique"):
            question = first_contact_request(role, taking_office=True) + "\n\nDemande de l'entraîneur : " + question
        if not question.startswith("[Message automatique"):
            original = question
            previous = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), None)
            kind = message_kind(question, previous)
            if kind == "reponse" and AGREE_RE.search(question):
                kind = "accord"
            question += "\n\n" + KIND_HINTS[kind]
            owner = topic_owner(original, role)
            if owner and not (role == "directeur_technique" and self._mentions_player(tctx, original)):
                other = team.get(owner)
                question += "\n\n" + redirect_hint(owner, other.name if other else None)
            unknown = unknown_people(self.engine, tctx.ctx.career_id, original)
            if unknown:
                question += "\n\n" + unknown_hint(unknown)
            facts = people_facts(self.engine, tctx.ctx.career_id, tctx.ctx.club_uid, original, tctx.prefs.currency.format)
            if facts:
                question += "\n\n" + facts_hint(facts)
            if OFF_TOPIC_RE.search(original) and not owner:
                question += "\n\n" + OFF_TOPIC_HINT
            if role == "directeur_technique" and self._mentions_player(tctx, question):
                adj, ds = team.get("entraineur_adjoint"), team.get(DIRECTOR)
                question += ("\n\n[Consigne automatique : la question porte sur un joueur, ce n'est pas ton métier. "
                             f"Réponds en une ou deux phrases que c'est le domaine de {adj.name if adj else 'l’adjoint'} "
                             f"(terrain, forme, temps de jeu) ou de {ds.name if ds else 'le directeur sportif'} (contrat, "
                             "marché), sans donner toi-même de statistiques ni d'avis sur le joueur, puis propose l'angle "
                             "staff si c'est pertinent.]")
        for note in notes or ():
            question += "\n\n" + note
        messages = _alternate([{"role": "user", "content": context}, *history, {"role": "user", "content": question}])
        return system, messages

    def _llm(self, tctx: ToolContext, question: str, history: list[dict], conv: int, trace: list[dict],
             force_tier: int | None, taking_office: bool = False, member=None, role: str = DIRECTOR,
             on_event: Event | None = None, notes: list[str] | None = None) -> ChatAnswer:
        provider = self.choose_provider(question, force_tier)
        if provider is None:
            text = ("Cette question demande une analyse par le modèle IA, mais aucun moteur n'est disponible "
                    "(non configuré, mode local sans serveur, ou budget mensuel atteint). Les questions factuelles "
                    "(scores, buteurs, classement, budgets, effectif par poste) restent disponibles sans IA.")
            if on_event:
                on_event({"type": "delta", "text": text})
            return ChatAnswer(text, "indisponible", conv, trace)
        system, messages = self._prompt(tctx, role, member, history, question, taking_office, conv, notes)
        last_said = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), None)
        lineup_args = (lineup_request(question, last_said) if role == "entraineur_adjoint"  # la composition, c'est l'adjoint
                       and not question.startswith("[Message automatique") else None)
        if lineup_args is not None and self.registry.get("propose_lineup") is not None:
            if on_event:
                on_event({"type": "tool", "name": "propose_lineup", "label": tool_label("propose_lineup")})
            r = self.registry.execute("propose_lineup", lineup_args, tctx)
            trace.append({"tool": "propose_lineup", "args": lineup_args, "ok": r.ok, "error": r.error})
            if r.ok:
                messages[-1] = {"role": "user", "content": messages[-1]["content"] + "\n\n" + lineup_brief(r.data)}
        if role == DIRECTOR and not question.startswith("[Message automatique") and message_kind(question, last_said) == "demande":
            # Achat demandé (offre pour un joueur d'un autre club) : plan préparé AVANT le modèle, dossier ouvert, chiffres
            # imposés. Vente, prolongation et contre-offre de nos joueurs : préchargées plus bas (ai/prefetch.py).
            op = self._operation(tctx, question)
            if op is not None:
                tool, args = op
                if on_event:
                    on_event({"type": "tool", "name": tool, "label": tool_label(tool)})
                r = self.registry.execute(tool, args, tctx)
                trace.append({"tool": tool, "args": args, "ok": r.ok, "error": r.error})
                if r.ok:
                    self._open_dossier(tctx, tool, args, r, role, conv)
                    messages[-1] = {"role": "user", "content": messages[-1]["content"] + "\n\n" + operation_brief(tool, r.data)}
        tools = self._tools_for(role)
        restricted = ROLE_TOOLS.get(role)  # None : tous les outils (les actions non prouvées restent refusées par le registre)
        cost = 0.0
        limitations: list[str] = []
        said: list[str] = []
        if lineup_args is None and not question.startswith("[Message automatique"):
            # Demandes courantes sur un joueur nommé : l'outil tourne avant le modèle, qui répond en un seul tour.
            for name, args in prefetch_calls(role, question, tctx, restricted):
                if self.registry.get(name) is None:
                    continue
                if on_event:
                    on_event({"type": "tool", "name": name, "label": tool_label(name)})
                r = self.registry.execute(name, args, tctx)
                trace.append({"tool": name, "args": args, "ok": r.ok, "error": r.error})
                if r.ok:
                    if name in DOSSIER_TOOLS:
                        self._open_dossier(tctx, name, args, r, role, conv)
                    limitations.extend(r.limitations)
                    messages[-1] = {"role": "user", "content": messages[-1]["content"] + "\n\n" + prefetch_brief(name, r.data)}
        with self._active_lock:
            self._active += 1
        try:
            session = provider.start(system, messages, tools)
            if hasattr(session, "thinking"):
                session.thinking = self._wants_thinking(question)
            stream = getattr(session, "step_stream", None) if on_event else None
            for _ in range(self.max_tool_rounds + 1):
                if stream is not None:
                    step = stream(lambda d: on_event({"type": "delta", "text": d}))
                else:
                    step = session.step()
                    if on_event and step.text:
                        on_event({"type": "delta", "text": step.text})
                cost += self._record_usage(provider, step.model, step.input_tokens, step.output_tokens)
                if step.text.strip():
                    said.append(step.text.strip())
                if not step.tool_calls:
                    return ChatAnswer("\n\n".join(said) or "(réponse vide du modèle)", f"niveau{provider.tier}", conv,
                                      trace, sorted(set(limitations)), provider.name, cost)
                if on_event:
                    on_event({"type": "break"})
                results = []
                for call in step.tool_calls:
                    if on_event:
                        on_event({"type": "tool", "name": call.name, "label": tool_label(call.name)})
                    if restricted is not None and call.name not in restricted:
                        r = ToolResult(call.name, False, error="Outil hors de ton rôle : renvoie l'entraîneur vers le bon interlocuteur.")
                    else:
                        r = self.registry.execute(call.name, call.arguments, tctx)
                        if r.ok and call.name in DOSSIER_TOOLS:
                            self._open_dossier(tctx, call.name, call.arguments, r, role, conv)
                    trace.append({"tool": call.name, "args": call.arguments, "ok": r.ok, "error": r.error})
                    limitations.extend(r.limitations)
                    payload = json.dumps(r.as_dict(), ensure_ascii=False, default=str, separators=(",", ":"))
                    results.append((call, _compact(payload), not r.ok))
                session.add_tool_results(results)
            said.append("J'ai atteint la limite d'appels d'outils sans conclure ; reformulez ou précisez la demande.")
            return ChatAnswer("\n\n".join(said), f"niveau{provider.tier}", conv, trace, sorted(set(limitations)),
                              provider.name, cost)
        except ProviderError as exc:
            log.warning("Fournisseur IA en échec : %s", exc)
            text = f"Le moteur IA « {provider.name} » est indisponible : {exc}"
            if on_event:
                on_event({"type": "delta", "text": text})
            return ChatAnswer(text, "indisponible", conv, trace, sorted(set(limitations)), provider.name, cost)
        finally:
            with self._active_lock:
                self._active -= 1

    def _mentions_player(self, tctx: ToolContext, text: str) -> bool:
        """Vrai si le message cite un joueur de l'effectif (nom complet ou nom de famille)."""
        from clubdirector.text import fold

        words = set(re.findall(r"[\w'-]+", fold(text)))
        try:
            squad = tctx.repo.squad(tctx.ctx, team_slot=None)
        except Exception:  # noqa: BLE001
            return False
        for p in squad:
            parts = [w for w in re.findall(r"[\w'-]+", fold(p["name"])) if len(w) > 2]
            if parts and parts[-1] in words:
                return True
        return False

    def _tools_for(self, role: str) -> list[dict]:
        allowed = ROLE_TOOLS.get(role)
        return [{"name": t.name, "description": t.description, "parameters": t.json_schema()}
                for t in self.registry.for_llm() if allowed is None or t.name in allowed]

    # ------------------------------------------------------------------ rapidité
    def warm(self, tctx: ToolContext, roles: tuple[str, ...] = CONTACT_ROLES) -> list[str]:
        """Pré-calcule le prompt de chaque contact (après une synchronisation) sur le modèle local.

        S'interrompt dès qu'une vraie conversation est en cours. Renvoie les rôles préparés."""
        provider = self.choose_provider("", 1)
        if provider is None or not hasattr(provider, "warm") or provider.input_cost_per_mtok > 0:
            return []
        done = []
        for role in roles:
            if self._active:
                break
            member = self.staff(tctx, role)
            conv = self.conversations.find_thread(tctx.ctx.career_id, role, member.uid if member else 0)
            system, messages = self._prompt(tctx, role, member, [], ".", conv=conv)
            tools = self._tools_for(role)
            key = hashlib.sha256(json.dumps([system, messages, tools], ensure_ascii=False, default=str)
                                 .encode("utf-8")).hexdigest()
            if self._warmed.get(role) == key:
                continue  # prompt inchangé depuis le dernier calcul : rien à refaire
            try:
                provider.warm(system, messages, tools)
            except ProviderError as exc:
                log.info("Préchauffage interrompu : %s", exc)
                break
            self._warmed[role] = key
            done.append(role)
        return done
