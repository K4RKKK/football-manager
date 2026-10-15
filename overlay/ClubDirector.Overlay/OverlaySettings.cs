using System.Text.Json;
using System.Text.Json.Serialization;

namespace ClubDirector.Overlay;

/// <summary>Réglages de la fenêtre, dans %LOCALAPPDATA%\ClubDirectorAI\overlay.json (créé au premier lancement).</summary>
public sealed class OverlaySettings
{
    /// <summary>Raccourci global : modificateurs (Ctrl, Alt, Shift, Win) + touche, ex. « Ctrl+Alt+D », « F10 ».</summary>
    public string Hotkey { get; set; } = "Ctrl+Alt+D";
    public int Width { get; set; } = 460;
    /// <summary>« right » ou « left ».</summary>
    public string Side { get; set; } = "right";
    public double Opacity { get; set; } = 1.0;
    /// <summary>Seuls 127.0.0.1 et localhost sont acceptés (service local).</summary>
    public string Url { get; set; } = "http://127.0.0.1:8765/overlay";
    public bool StartHidden { get; set; }

    [JsonIgnore] public static string DataDir =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ClubDirectorAI");
    [JsonIgnore] public static string FilePath => Path.Combine(DataDir, "overlay.json");

    private static readonly JsonSerializerOptions Json = new() { WriteIndented = true, PropertyNameCaseInsensitive = true };

    public static OverlaySettings Load()
    {
        try
        {
            if (File.Exists(FilePath))
                return Normalize(JsonSerializer.Deserialize<OverlaySettings>(File.ReadAllText(FilePath), Json) ?? new());
        }
        catch (Exception)
        {
            // Fichier illisible : valeurs par défaut, le fichier de l'utilisateur n'est pas écrasé.
            return new OverlaySettings();
        }
        var s = new OverlaySettings();
        s.Save();
        return s;
    }

    public void Save()
    {
        try
        {
            Directory.CreateDirectory(DataDir);
            File.WriteAllText(FilePath, JsonSerializer.Serialize(this, Json));
        }
        catch (Exception)
        {
            // Réglages non enregistrés : la fenêtre fonctionne quand même.
        }
    }

    private static OverlaySettings Normalize(OverlaySettings s)
    {
        s.Width = Math.Clamp(s.Width, 320, 1200);
        s.Opacity = Math.Clamp(s.Opacity, 0.6, 1.0);
        if (!Uri.TryCreate(s.Url, UriKind.Absolute, out var u) || !(u.Host is "127.0.0.1" or "localhost"))
            s.Url = new OverlaySettings().Url;
        return s;
    }
}
