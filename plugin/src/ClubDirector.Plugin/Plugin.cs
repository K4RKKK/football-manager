using System;
using System.Threading;
using System.Threading.Tasks;
using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using ClubDirector.Core;
using Il2CppInterop.Runtime.Injection;
using UnityEngine;

namespace ClubDirector.Plugin
{
    /// <summary>
    /// Point d'entrée BepInEx. STATUT : NON VALIDÉ DANS FM26 (écrit d'après les techniques éprouvées
    /// de FM26Access/FMSuperScout ; à tester sur le PC de l'utilisateur, voir docs/TEST_PLAN.md P-1..P-4).
    ///
    /// Principes : aucune opération longue sur le thread principal ; toute la communication réseau
    /// est sur des tâches de fond ; l'UI n'est modifiée que via MainThreadDispatcher dans Update().
    /// Le plugin ne lit pas la mémoire du jeu et n'écrit jamais dans la sauvegarde.
    /// </summary>
    [BepInPlugin(Guid, Name, Version)]
    public class Plugin : BasePlugin
    {
        public const string Guid = "ai.clubdirector.fm26";
        public const string Name = "ClubDirector AI";
        public const string Version = "0.1.0";

        internal static ManualLogSource Logger;
        internal static MainThreadDispatcher Dispatcher;
        internal static ChatSession Chat;
        internal static BackendClient Client;
        internal static ConfigEntry<UnityEngine.InputSystem.Key> ToggleKey;
        internal static volatile bool BackendOnline;
        internal static volatile string BackendStatus = "Service ClubDirector non contacté";

        private static GameObject _host;
        private static string _gameVersion;
        private CancellationTokenSource _cts;

        public override void Load()
        {
            Logger = Log;
            var port = Config.Bind("Service", "Port", 8765, "Port du service local ClubDirector (127.0.0.1).");
            ToggleKey = Config.Bind("Interface", "Raccourci", UnityEngine.InputSystem.Key.F10,
                "Touche d'ouverture du panneau Directeur sportif IA (F7 : The Director, F9 : FMSuperScout/Player Export).");
            _gameVersion = Application.version; // API Unity : lue sur le thread principal uniquement
            Dispatcher = new MainThreadDispatcher(ex => Log.LogWarning("[ClubDirector] action UI en échec : " + ex.Message));

            try
            {
                var token = BackendClient.ReadToken(BackendClient.DefaultDataDir());
                Client = new BackendClient(port.Value, token);
                Chat = new ChatSession(Client, Dispatcher);
            }
            catch (Exception ex)
            {
                BackendStatus = ex.Message;
                Log.LogWarning("[ClubDirector] " + ex.Message);
            }

            ClassInjector.RegisterTypeInIl2Cpp<DirectorBehaviour>();
            _host = new GameObject("ClubDirectorAI");
            UnityEngine.Object.DontDestroyOnLoad(_host);
            _host.hideFlags = HideFlags.HideAndDontSave;
            _host.AddComponent<DirectorBehaviour>();

            _cts = new CancellationTokenSource();
            if (Client != null) Task.Run(() => HeartbeatLoop(_cts.Token));
            Log.LogInfo($"[ClubDirector] v{Version} chargé — panneau : {ToggleKey.Value}");
        }

        public override bool Unload()
        {
            _cts?.Cancel();
            DirectorOverlay.Destroy();
            Client?.Dispose();
            return true;
        }

        private static async Task HeartbeatLoop(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    var screen = GameProbe.LastScreenName; // lu sur le thread principal, copié ici
                    await Client.HeartbeatAsync(new HeartbeatPayload
                    {
                        PluginVersion = Version,
                        GameVersion = _gameVersion,
                        State = "connecte",
                        CurrentScreen = screen,
                        Detail = "Détection du chargement de carrière : non implémentée (voir TECHNICAL_FEASIBILITY.md).",
                    }, ct).ConfigureAwait(false);
                    BackendOnline = true;
                    BackendStatus = "Service ClubDirector connecté";
                }
                catch (Exception ex)
                {
                    BackendOnline = false;
                    BackendStatus = ex.Message;
                }
                try { await Task.Delay(TimeSpan.FromSeconds(5), ct).ConfigureAwait(false); }
                catch (TaskCanceledException) { return; }
            }
        }
    }
}
