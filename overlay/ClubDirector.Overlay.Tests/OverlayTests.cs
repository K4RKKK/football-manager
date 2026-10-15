using System.Text.Json;
using ClubDirector.Overlay;
using Xunit;

public class OverlayTests
{
    [Theory]
    [InlineData("Ctrl+Alt+D", Keys.D)]
    [InlineData("F10", Keys.F10)]
    [InlineData("ctrl + shift + Space", Keys.Space)]
    public void Hotkeys_are_parsed(string text, Keys key)
    {
        var (mods, k) = GlobalHotkey.Parse(text);
        Assert.Equal(key, k);
        Assert.True((mods & 0x4000) != 0); // MOD_NOREPEAT : pas de répétition en maintenant la touche
    }

    [Theory]
    [InlineData("Ctrl+Alt")]
    [InlineData("Ctrl+Tralala")]
    public void Invalid_hotkeys_are_rejected(string text) =>
        Assert.Throws<FormatException>(() => GlobalHotkey.Parse(text));

    [Fact]
    public void Settings_only_accept_the_local_service()
    {
        var path = Path.Combine(Path.GetTempPath(), "cd-overlay-test.json");
        var s = JsonSerializer.Deserialize<OverlaySettings>("{\"Url\":\"https://exemple.com/\",\"Width\":5000,\"Opacity\":0.1}")!;
        var normalized = typeof(OverlaySettings).GetMethod("Normalize", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static)!
            .Invoke(null, new object[] { s }) as OverlaySettings;
        Assert.Equal("http://127.0.0.1:8765/overlay", normalized!.Url);
        Assert.Equal(1200, normalized.Width);
        Assert.Equal(0.6, normalized.Opacity);
    }
}
