using System;
using UnityEngine.UIElements;

namespace ClubDirector.Plugin
{
    /// <summary>
    /// Lecture légère du contexte d'écran (lecture seule). Approche reprise de FM26Access
    /// (UIContextDetector) : document « PanelManager » → emplacement « Menu » → premier écran.
    /// Ne lit aucune donnée de joueur : les données viennent de la sauvegarde via le service.
    /// </summary>
    internal static class GameProbe
    {
        public static volatile string LastScreenName;

        public static void Refresh()
        {
            try
            {
                foreach (var doc in UnityEngine.Object.FindObjectsOfType<UIDocument>())
                {
                    if (doc == null || doc.gameObject == null || doc.gameObject.name != "PanelManager") continue;
                    var root = doc.rootVisualElement;
                    var menu = root?.Q("Menu");
                    if (menu == null || menu.childCount == 0) return;
                    LastScreenName = menu.ElementAt(0)?.name;
                    return;
                }
            }
            catch (Exception)
            {
                LastScreenName = null; // structure UI différente : on n'invente rien
            }
        }
    }
}
