using System;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace ClubDirector.Core
{
    /// <summary>Réponse du directeur sportif (miroir de ChatAnswer côté Python).</summary>
    public sealed class ChatAnswer
    {
        [JsonPropertyName("text")] public string Text { get; set; } = "";
        [JsonPropertyName("route")] public string Route { get; set; } = "";
        [JsonPropertyName("conversation_id")] public int ConversationId { get; set; }
        [JsonPropertyName("limitations")] public string[] Limitations { get; set; } = Array.Empty<string>();
        [JsonPropertyName("provider")] public string? Provider { get; set; }
    }

    public sealed class HeartbeatPayload
    {
        [JsonPropertyName("plugin_version")] public string PluginVersion { get; set; } = "";
        [JsonPropertyName("game_version")] public string? GameVersion { get; set; }
        [JsonPropertyName("state")] public string State { get; set; } = "connecte";
        [JsonPropertyName("current_screen")] public string? CurrentScreen { get; set; }
        [JsonPropertyName("in_match")] public bool InMatch { get; set; }
        [JsonPropertyName("detail")] public string? Detail { get; set; }
    }

    public sealed class HeartbeatReply
    {
        [JsonPropertyName("ok")] public bool Ok { get; set; }
        [JsonPropertyName("server_version")] public string? ServerVersion { get; set; }
        [JsonPropertyName("silent")] public bool Silent { get; set; }
    }

    public sealed class BackendException : Exception
    {
        public BackendException(string message, Exception? inner = null) : base(message, inner) { }
    }

    /// <summary>
    /// Client HTTP du service local ClubDirector (127.0.0.1 uniquement).
    /// Toutes les méthodes sont asynchrones : ne JAMAIS les attendre sur le thread principal d'Unity.
    /// </summary>
    public sealed class BackendClient : IDisposable
    {
        private readonly HttpClient _http;
        private readonly string _token;

        public Uri BaseUri { get; }

        public BackendClient(int port, string token, HttpMessageHandler? handler = null, TimeSpan? timeout = null)
        {
            if (string.IsNullOrWhiteSpace(token)) throw new ArgumentException("Jeton vide", nameof(token));
            BaseUri = new Uri($"http://127.0.0.1:{port}/");
            _token = token;
            _http = handler == null ? new HttpClient() : new HttpClient(handler);
            _http.BaseAddress = BaseUri;
            _http.Timeout = timeout ?? TimeSpan.FromSeconds(180);
        }

        /// <summary>Lit le jeton partagé écrit par le service (%LOCALAPPDATA%\ClubDirectorAI\plugin.token).</summary>
        public static string ReadToken(string dataDir)
        {
            var path = Path.Combine(dataDir, "plugin.token");
            if (!File.Exists(path))
                throw new BackendException($"Jeton introuvable ({path}) : lancez d'abord le service ClubDirector.");
            return File.ReadAllText(path, Encoding.UTF8).Trim();
        }

        public static string DefaultDataDir()
        {
            var env = Environment.GetEnvironmentVariable("CLUBDIRECTOR_HOME");
            if (!string.IsNullOrEmpty(env)) return env!;
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ClubDirectorAI");
        }

        public Task<HeartbeatReply> HeartbeatAsync(HeartbeatPayload hb, CancellationToken ct = default)
            => PostAsync<HeartbeatReply>("api/plugin/heartbeat", hb, ct);

        public Task<ChatAnswer> AskAsync(string question, int? conversationId, CancellationToken ct = default)
        {
            if (string.IsNullOrWhiteSpace(question)) throw new ArgumentException("Question vide", nameof(question));
            return PostAsync<ChatAnswer>("api/chat", new { question, conversation_id = conversationId }, ct);
        }

        public async Task<JsonDocument> GetJsonAsync(string path, CancellationToken ct = default)
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, path);
            var body = await SendAsync(req, ct).ConfigureAwait(false);
            return JsonDocument.Parse(body);
        }

        private async Task<T> PostAsync<T>(string path, object payload, CancellationToken ct)
        {
            using var req = new HttpRequestMessage(HttpMethod.Post, path)
            {
                Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json"),
            };
            var body = await SendAsync(req, ct).ConfigureAwait(false);
            return JsonSerializer.Deserialize<T>(body) ?? throw new BackendException("Réponse vide du service.");
        }

        private async Task<string> SendAsync(HttpRequestMessage req, CancellationToken ct)
        {
            req.Headers.Add("X-ClubDirector-Token", _token);
            HttpResponseMessage resp;
            try
            {
                resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
            }
            catch (Exception ex) when (ex is HttpRequestException || ex is TaskCanceledException)
            {
                throw new BackendException("Service ClubDirector injoignable sur " + BaseUri, ex);
            }
            using (resp)
            {
                var body = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
                if (!resp.IsSuccessStatusCode)
                {
                    string detail = body;
                    try { detail = JsonDocument.Parse(body).RootElement.GetProperty("detail").ToString(); } catch (Exception) { }
                    throw new BackendException($"Service ClubDirector : {(int)resp.StatusCode} {detail}");
                }
                return body;
            }
        }

        public void Dispose() => _http.Dispose();
    }
}
