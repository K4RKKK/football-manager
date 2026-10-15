using System;
using System.Threading.Tasks;
using ClubDirector.Core;
using Xunit;

/// <summary>
/// Test inter-langages : client C# du plugin ↔ vrai service Python. Exécuté par
/// scripts/e2e_plugin_backend.sh (qui lance le service sur une carrière synthétique) ;
/// ignoré si CLUBDIRECTOR_E2E_PORT n'est pas défini.
/// </summary>
public class EndToEndTests
{
    private static int? Port => int.TryParse(Environment.GetEnvironmentVariable("CLUBDIRECTOR_E2E_PORT"), out var p) ? p : null;

    [Fact]
    public async Task Plugin_client_talks_to_real_backend()
    {
        if (Port is null) return; // non configuré : test neutre
        var token = BackendClient.ReadToken(BackendClient.DefaultDataDir());
        using var c = new BackendClient(Port.Value, token);
        var hb = await c.HeartbeatAsync(new HeartbeatPayload { PluginVersion = "0.1.0-e2e", GameVersion = "26.3.2", InMatch = true });
        Assert.True(hb.Ok);
        Assert.True(hb.Silent);
        var a = await c.AskAsync("Quel était notre score il y a une semaine ?", null);
        Assert.Equal("niveau0", a.Route);
        Assert.Contains("3-1", a.Text);
        using var st = await c.GetJsonAsync("api/plugin/status");
        Assert.Equal("connecte", st.RootElement.GetProperty("state").GetString());
        using var bad = new BackendClient(Port.Value, "mauvais-jeton");
        await Assert.ThrowsAsync<BackendException>(() => bad.AskAsync("x", null));
    }
}
