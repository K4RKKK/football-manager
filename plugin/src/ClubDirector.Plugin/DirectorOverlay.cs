using System;
using ClubDirector.Core;
using Il2CppInterop.Runtime;
using UnityEngine;
using UnityEngine.UIElements;

namespace ClubDirector.Plugin
{
    /// <summary>
    /// Panneau « Directeur sportif IA » superposé à FM26 (UI Toolkit natif).
    /// Technique : GameObject + UIDocument utilisant les PanelSettings empruntés à un document du
    /// jeu, sortingOrder élevé (FM26Access, FocusHighlight.cs). Aucun navigateur embarqué.
    /// Étape suivante (expérimentale) : insérer un bouton dans le menu latéral de FM26 une fois
    /// sa structure relevée avec UiTreeDumper.
    /// </summary>
    internal static class DirectorOverlay
    {
        private static readonly Color Bg = new(0.043f, 0.078f, 0.106f, 0.97f);     // #0B141B
        private static readonly Color Surface = new(0.075f, 0.129f, 0.169f, 1f);   // #13212B
        private static readonly Color Border = new(0.149f, 0.235f, 0.271f, 1f);    // #263C45
        private static readonly Color Green = new(0.161f, 0.780f, 0.482f, 1f);     // #29C77B
        private static readonly Color Text = new(0.949f, 0.965f, 0.973f, 1f);      // #F2F6F8
        private static readonly Color Muted = new(0.608f, 0.682f, 0.722f, 1f);     // #9BAEB8
        private static readonly Color Error = new(0.890f, 0.431f, 0.459f, 1f);     // #E36E75

        private static GameObject _go;
        private static VisualElement _panel;
        private static ScrollView _messages;
        private static TextField _input;
        private static Label _status;
        private static bool _visible;

        public static void Toggle()
        {
            if (!EnsureCreated()) return;
            _visible = !_visible;
            _panel.style.display = _visible ? DisplayStyle.Flex : DisplayStyle.None;
            if (_visible) { Render(); _input?.Focus(); }
        }

        public static void Destroy()
        {
            if (_go != null) { try { UnityEngine.Object.Destroy(_go); } catch (Exception) { } }
            _go = null; _panel = null; _messages = null; _input = null; _status = null;
        }

        private static bool EnsureCreated()
        {
            if (_go != null)
            {
                try { _ = _go.name; return true; } catch (Exception) { Destroy(); }
            }
            PanelSettings settings = null;
            foreach (var doc in UnityEngine.Object.FindObjectsOfType<UIDocument>())
            {
                if (doc != null && doc.panelSettings != null) { settings = doc.panelSettings; break; }
            }
            if (settings == null)
            {
                Plugin.Logger.LogWarning("[ClubDirector] Aucun PanelSettings trouvé : panneau indisponible sur cet écran.");
                return false;
            }
            _go = new GameObject("ClubDirectorAI_Overlay");
            UnityEngine.Object.DontDestroyOnLoad(_go);
            _go.hideFlags = HideFlags.HideAndDontSave;
            var ui = _go.AddComponent<UIDocument>();
            ui.panelSettings = settings;
            ui.sortingOrder = 30500;
            var root = ui.rootVisualElement;
            root.pickingMode = PickingMode.Ignore;
            root.style.position = Position.Absolute;
            root.style.left = 0; root.style.top = 0; root.style.right = 0; root.style.bottom = 0;

            _panel = new VisualElement { name = "cd-panel" };
            _panel.style.position = Position.Absolute;
            _panel.style.right = 16; _panel.style.top = 64; _panel.style.bottom = 16;
            _panel.style.width = 460;
            _panel.style.backgroundColor = Bg;
            SetBorder(_panel, Border, 10);
            _panel.style.paddingLeft = 14; _panel.style.paddingRight = 14; _panel.style.paddingTop = 12; _panel.style.paddingBottom = 12;
            _panel.style.flexDirection = FlexDirection.Column;
            _panel.style.display = DisplayStyle.None;
            root.Add(_panel);

            var header = new VisualElement();
            header.style.flexDirection = FlexDirection.Row;
            header.style.alignItems = Align.Center;
            var title = new Label("Directeur sportif IA");
            title.style.color = Text; title.style.fontSize = 18; title.style.unityFontStyleAndWeight = FontStyle.Bold;
            title.style.flexGrow = 1;
            header.Add(title);
            header.Add(MakeButton("Nouvelle", () => { Plugin.Chat?.Reset(); }, false));
            header.Add(MakeButton("✕", () => Toggle(), false));
            _panel.Add(header);

            _status = new Label();
            _status.style.color = Muted; _status.style.fontSize = 11; _status.style.marginBottom = 8;
            _panel.Add(_status);

            _messages = new ScrollView(ScrollViewMode.Vertical);
            _messages.style.flexGrow = 1;
            _messages.style.backgroundColor = Surface;
            SetBorder(_messages, Border, 8);
            _messages.style.paddingLeft = 8; _messages.style.paddingRight = 8; _messages.style.paddingTop = 8;
            _panel.Add(_messages);

            var row = new VisualElement();
            row.style.flexDirection = FlexDirection.Row;
            row.style.marginTop = 8;
            _input = new TextField { multiline = true };
            _input.style.flexGrow = 1; _input.style.minHeight = 44;
            row.Add(_input);
            row.Add(MakeButton("Envoyer", Send, true));
            _panel.Add(row);

            if (Plugin.Chat != null)
                Plugin.Chat.Changed += Render;
            return true;
        }

        private static void Send()
        {
            if (Plugin.Chat == null) { Render(); return; }
            var q = _input?.value ?? "";
            if (Plugin.Chat.Send(q)) _input.value = "";
        }

        private static Button MakeButton(string label, Action onClick, bool primary)
        {
            var b = new Button { text = label };
            b.style.marginLeft = 6;
            b.style.color = primary ? new Color(0.02f, 0.07f, 0.05f) : Text;
            b.style.backgroundColor = primary ? Green : Surface;
            SetBorder(b, primary ? Green : Border, 6);
            b.RegisterCallback(DelegateSupport.ConvertDelegate<EventCallback<ClickEvent>>(
                new Action<ClickEvent>(_ =>
                {
                    try { onClick(); }
                    catch (Exception ex) { Plugin.Logger.LogWarning("[ClubDirector] clic : " + ex.Message); }
                })), TrickleDown.NoTrickleDown);
            return b;
        }

        private static void SetBorder(VisualElement e, Color c, float radius)
        {
            e.style.borderTopColor = c; e.style.borderBottomColor = c; e.style.borderLeftColor = c; e.style.borderRightColor = c;
            e.style.borderTopWidth = 1; e.style.borderBottomWidth = 1; e.style.borderLeftWidth = 1; e.style.borderRightWidth = 1;
            e.style.borderTopLeftRadius = radius; e.style.borderTopRightRadius = radius;
            e.style.borderBottomLeftRadius = radius; e.style.borderBottomRightRadius = radius;
        }

        private static void Render()
        {
            if (_messages == null) return;
            _status.text = Plugin.BackendStatus + (Plugin.Chat?.Busy == true ? " · le directeur sportif consulte les données…" : "");
            _status.style.color = Plugin.BackendOnline ? Muted : Error;
            _messages.Clear();
            if (Plugin.Chat == null)
            {
                _messages.Add(Line("Service ClubDirector indisponible : lancez « clubdirector serve » puis rouvrez FM26.", Error, false));
                return;
            }
            foreach (var l in Plugin.Chat.Lines)
            {
                var color = l.Role == ChatRole.Error ? Error : Text;
                _messages.Add(Line(l.Text + (l.Meta != null ? "\n[" + l.Meta + "]" : ""), color, l.Role == ChatRole.User));
            }
        }

        private static Label Line(string text, Color color, bool user)
        {
            var label = new Label(text);
            label.style.whiteSpace = WhiteSpace.Normal;
            label.style.color = color;
            label.style.marginBottom = 8;
            label.style.paddingLeft = 8; label.style.paddingRight = 8; label.style.paddingTop = 6; label.style.paddingBottom = 6;
            label.style.backgroundColor = user ? new Color(0.114f, 0.29f, 0.212f, 1f) : Bg;
            label.style.alignSelf = user ? Align.FlexEnd : Align.FlexStart;
            SetBorder(label, Border, 8);
            return label;
        }
    }
}
