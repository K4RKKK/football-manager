using System.Runtime.InteropServices;

namespace ClubDirector.Overlay;

/// <summary>Raccourci clavier global (RegisterHotKey) : fonctionne même quand FM26 a le focus.</summary>
public static class GlobalHotkey
{
    public const int WM_HOTKEY = 0x0312;
    private const uint MOD_ALT = 0x1, MOD_CONTROL = 0x2, MOD_SHIFT = 0x4, MOD_WIN = 0x8, MOD_NOREPEAT = 0x4000;

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    /// <summary>Analyse « Ctrl+Alt+D » ; lève FormatException si la touche est inconnue.</summary>
    public static (uint Modifiers, Keys Key) Parse(string text)
    {
        uint mods = 0;
        Keys? key = null;
        foreach (var raw in text.Split('+', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            switch (raw.ToLowerInvariant())
            {
                case "ctrl": case "control": mods |= MOD_CONTROL; break;
                case "alt": mods |= MOD_ALT; break;
                case "shift": case "maj": mods |= MOD_SHIFT; break;
                case "win": mods |= MOD_WIN; break;
                default:
                    if (!Enum.TryParse<Keys>(raw, true, out var k)) throw new FormatException($"Touche inconnue : {raw}");
                    key = k;
                    break;
            }
        }
        if (key is null) throw new FormatException("Aucune touche dans le raccourci.");
        return (mods | MOD_NOREPEAT, key.Value);
    }

    public static bool Register(IntPtr hwnd, int id, string text)
    {
        var (mods, key) = Parse(text);
        return RegisterHotKey(hwnd, id, mods, (uint)key);
    }

    public static void Unregister(IntPtr hwnd, int id) => UnregisterHotKey(hwnd, id);
}
