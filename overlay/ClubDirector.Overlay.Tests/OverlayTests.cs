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

public class PhoneLayoutTests
{
    private static readonly Rectangle Screen1080 = new(0, 0, 1920, 1040);

    [Fact]
    public void Phone_is_placed_on_the_right_and_vertically_centered()
    {
        var r = PhoneLayout.Compute(Screen1080, 860, 1.0, null);
        Assert.Equal(860, r.Height);
        Assert.Equal((int)Math.Round(860 * PhoneLayout.Ratio), r.Width);
        Assert.Equal(1920 - r.Width - 24, r.X);
        Assert.Equal((1040 - 860) / 2, r.Y);
    }

    [Fact]
    public void Phone_never_exceeds_the_screen_and_follows_the_dpi()
    {
        Assert.Equal(1040 - 16, PhoneLayout.Compute(Screen1080, 1400, 1.0, null).Height);
        Assert.Equal(1024, PhoneLayout.Compute(new Rectangle(0, 0, 2560, 1400), 860, 1.25, null).Height - 51);
    }

    [Fact]
    public void A_saved_position_is_kept_only_if_still_on_screen()
    {
        Assert.Equal(new Point(300, 100), PhoneLayout.Compute(Screen1080, 860, 1.0, new Point(300, 100)).Location);
        var lost = PhoneLayout.Compute(Screen1080, 860, 1.0, new Point(5000, 100));
        Assert.Equal(1920 - lost.Width - 24, lost.X);
    }

    [Fact]
    public void Phone_mode_is_the_default()
    {
        var s = JsonSerializer.Deserialize<OverlaySettings>("{}")!;
        Assert.True(s.IsPhone);
        Assert.False(JsonSerializer.Deserialize<OverlaySettings>("{\"Mode\":\"panneau\"}")!.IsPhone);
    }
}
