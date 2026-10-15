using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ClubDirector.Core;
using Xunit;

public class FakeHandler : HttpMessageHandler
{
    public HttpRequestMessage? Last;
    public string? LastBody;
    private readonly Func<HttpRequestMessage, HttpResponseMessage> _respond;
    public FakeHandler(Func<HttpRequestMessage, HttpResponseMessage> respond) => _respond = respond;

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        Last = request;
        LastBody = request.Content == null ? null : await request.Content.ReadAsStringAsync(ct);
        return _respond(request);
    }
}

public class BackendClientTests
{
    static HttpResponseMessage Json(HttpStatusCode code, string body) =>
        new(code) { Content = new StringContent(body, Encoding.UTF8, "application/json") };

    [Fact]
    public async Task Ask_sends_token_and_parses_answer()
    {
        var h = new FakeHandler(_ => Json(HttpStatusCode.OK,
            "{\"text\":\"3-1\",\"route\":\"niveau0\",\"conversation_id\":7,\"limitations\":[],\"provider\":null}"));
        using var c = new BackendClient(8765, "secret", h);
        var a = await c.AskAsync("Score ?", null);
        Assert.Equal("3-1", a.Text);
        Assert.Equal(7, a.ConversationId);
        Assert.Equal("secret", h.Last!.Headers.GetValues("X-ClubDirector-Token").Single());
        Assert.Equal("http://127.0.0.1:8765/api/chat", h.Last.RequestUri!.ToString());
        Assert.Contains("\"question\":\"Score ?\"", h.LastBody);
    }

    [Fact]
    public async Task Http_error_is_surfaced_with_detail()
    {
        var h = new FakeHandler(_ => Json(HttpStatusCode.Unauthorized, "{\"detail\":\"Jeton invalide\"}"));
        using var c = new BackendClient(8765, "x", h);
        var ex = await Assert.ThrowsAsync<BackendException>(() => c.AskAsync("q", null));
        Assert.Contains("401", ex.Message);
        Assert.Contains("Jeton invalide", ex.Message);
    }

    [Fact]
    public async Task Unreachable_service_is_explicit()
    {
        var h = new FakeHandler(_ => throw new HttpRequestException("refused"));
        using var c = new BackendClient(8765, "x", h);
        var ex = await Assert.ThrowsAsync<BackendException>(() => c.HeartbeatAsync(new HeartbeatPayload { PluginVersion = "0.1" }));
        Assert.Contains("injoignable", ex.Message);
    }

    [Fact]
    public void Only_loopback_is_used() => Assert.Equal("127.0.0.1", new BackendClient(1234, "t").BaseUri.Host);

    [Fact]
    public void Token_file_is_required()
    {
        var dir = Directory.CreateTempSubdirectory().FullName;
        Assert.Throws<BackendException>(() => BackendClient.ReadToken(dir));
        File.WriteAllText(Path.Combine(dir, "plugin.token"), "abc\n");
        Assert.Equal("abc", BackendClient.ReadToken(dir));
    }
}

public class DispatcherTests
{
    [Fact]
    public void Drain_respects_max_and_survives_exceptions()
    {
        int errors = 0, ran = 0;
        var d = new MainThreadDispatcher(_ => errors++);
        d.Post(() => throw new InvalidOperationException());
        for (int i = 0; i < 10; i++) d.Post(() => ran++);
        Assert.Equal(5, d.Drain(TimeSpan.FromSeconds(1), maxActions: 5));
        Assert.Equal(1, errors);
        Assert.Equal(4, ran);
        d.Drain(TimeSpan.FromSeconds(1));
        Assert.Equal(10, ran);
        Assert.Equal(0, d.Pending);
    }
}

public class ChatSessionTests
{
    [Fact]
    public async Task Reply_is_applied_on_main_thread_queue_only()
    {
        var h = new FakeHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent("{\"text\":\"Bonjour coach\",\"route\":\"niveau1\",\"conversation_id\":3,\"limitations\":[\"limite\"]}"),
        });
        var d = new MainThreadDispatcher();
        var s = new ChatSession(new BackendClient(1, "t", h), d);
        Assert.True(s.Send("Bonjour"));
        Assert.False(s.Send("Deuxième message pendant l'envoi"));
        for (int i = 0; i < 100 && d.Pending == 0; i++) await Task.Delay(20);
        Assert.Single(s.Lines);  // la réponse n'est pas appliquée hors du thread principal
        d.Drain(TimeSpan.FromSeconds(1));
        Assert.Equal(2, s.Lines.Count);
        Assert.Equal(ChatRole.Director, s.Lines[1].Role);
        Assert.Contains("⚠ limite", s.Lines[1].Text);
        Assert.Equal(3, s.ConversationId);
        Assert.False(s.Busy);
    }

    [Fact]
    public async Task Backend_failure_becomes_error_line()
    {
        var h = new FakeHandler(_ => throw new HttpRequestException("down"));
        var d = new MainThreadDispatcher();
        var s = new ChatSession(new BackendClient(1, "t", h), d);
        s.Send("Bonjour");
        for (int i = 0; i < 100 && d.Pending == 0; i++) await Task.Delay(20);
        d.Drain(TimeSpan.FromSeconds(1));
        Assert.Equal(ChatRole.Error, s.Lines.Last().Role);
    }
}
