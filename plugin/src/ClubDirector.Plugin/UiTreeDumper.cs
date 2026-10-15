using System;
using System.IO;
using System.Text;
using Il2CppInterop.Runtime;
using UnityEngine.UIElements;

namespace ClubDirector.Plugin
{
    /// <summary>
    /// Outil de rétro-ingénierie : écrit l'arbre des VisualElement de FM26 dans un fichier texte
    /// (%LOCALAPPDATA%\ClubDirectorAI\ui-dump-*.txt) pour localiser le menu latéral gauche et y
    /// injecter l'entrée « Directeur sportif IA ». Parcours borné (8000 nœuds) : FM26Access signale
    /// que les arbres à liaisons lourdes peuvent figer IL2CPP.
    /// </summary>
    internal static class UiTreeDumper
    {
        private const int MaxNodes = 8000;
        private const int MaxDepth = 40;

        public static void DumpToFile()
        {
            var sb = new StringBuilder();
            int count = 0;
            try
            {
                foreach (var doc in UnityEngine.Object.FindObjectsOfType<UIDocument>())
                {
                    if (doc == null) continue;
                    sb.AppendLine($"# UIDocument '{doc.gameObject?.name}' sortingOrder={doc.sortingOrder}");
                    Walk(doc.rootVisualElement, 0, sb, ref count);
                    if (count >= MaxNodes) break;
                }
                var dir = ClubDirector.Core.BackendClient.DefaultDataDir();
                Directory.CreateDirectory(dir);
                var path = Path.Combine(dir, $"ui-dump-{DateTime.Now:yyyyMMdd-HHmmss}.txt");
                File.WriteAllText(path, sb.ToString(), Encoding.UTF8);
                Plugin.Logger.LogInfo($"[ClubDirector] Arbre UI ({count} nœuds) écrit dans {path}");
            }
            catch (Exception ex)
            {
                Plugin.Logger.LogWarning("[ClubDirector] Relevé UI impossible : " + ex.Message);
            }
        }

        private static void Walk(VisualElement el, int depth, StringBuilder sb, ref int count)
        {
            if (el == null || depth > MaxDepth || count >= MaxNodes) return;
            count++;
            string type;
            try { type = el.GetIl2CppType().Name; } catch (Exception) { type = "?"; }
            string classes = "";
            try { classes = string.Join(".", el.GetClasses()); } catch (Exception) { }
            string text = "";
            try
            {
                // Les proxys IL2CPP ne supportent pas « is » : TryCast obligatoire (cf. FM26Access).
                var te = el.TryCast<TextElement>();
                if (te != null && !string.IsNullOrEmpty(te.text)) text = " \"" + Trunc(te.text) + "\"";
            }
            catch (Exception) { }
            sb.Append(' ', depth * 2).Append(type).Append(" #").Append(el.name).Append(" .").Append(classes).Append(text).AppendLine();
            int n;
            try { n = el.childCount; } catch (Exception) { return; }
            for (int i = 0; i < n && count < MaxNodes; i++)
            {
                VisualElement child;
                try { child = el.ElementAt(i); } catch (Exception) { continue; }
                Walk(child, depth + 1, sb, ref count);
            }
        }

        private static string Trunc(string s) => s.Length > 60 ? s.Substring(0, 60) + "…" : s.Replace("\n", " ");
    }
}
