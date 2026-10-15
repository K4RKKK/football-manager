using System;
using UnityEngine;
using UnityEngine.InputSystem;

namespace ClubDirector.Plugin
{
    /// <summary>
    /// MonoBehaviour injecté : draine la file du thread principal (budget 2 ms/image), gère le
    /// raccourci clavier et le diagnostic de l'arbre UI.
    /// </summary>
    public class DirectorBehaviour : MonoBehaviour
    {
        public DirectorBehaviour(IntPtr ptr) : base(ptr) { }

        private float _nextProbe;

        private void Update()
        {
            try
            {
                Plugin.Dispatcher.Drain(TimeSpan.FromMilliseconds(2));

                var kb = Keyboard.current;
                if (kb != null)
                {
                    bool shift = kb.leftShiftKey.isPressed || kb.rightShiftKey.isPressed;
                    if (kb[Plugin.ToggleKey.Value].wasPressedThisFrame)
                    {
                        if (shift) UiTreeDumper.DumpToFile();   // Maj+F10 : relevé de l'arbre UI (rétro-ingénierie)
                        else DirectorOverlay.Toggle();
                    }
                }

                if (Time.unscaledTime >= _nextProbe)
                {
                    _nextProbe = Time.unscaledTime + 2f;
                    GameProbe.Refresh();
                }
            }
            catch (Exception ex)
            {
                Plugin.Logger.LogWarning("[ClubDirector] Update : " + ex.Message);
            }
        }
    }
}
