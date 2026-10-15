using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace ClubDirector.Core
{
    public enum ChatRole { User, Director, Error }

    public sealed record ChatLine(ChatRole Role, string Text, string? Meta = null);

    /// <summary>
    /// État de la discussion affichée dans l'overlay. L'envoi se fait en arrière-plan ; les mises à
    /// jour de l'UI sont renvoyées au thread principal via le dispatcher.
    /// </summary>
    public sealed class ChatSession
    {
        private readonly BackendClient _client;
        private readonly MainThreadDispatcher _dispatcher;
        private readonly List<ChatLine> _lines = new();
        private int _busy;

        public int? ConversationId { get; private set; }
        public bool Busy => Volatile.Read(ref _busy) == 1;
        public IReadOnlyList<ChatLine> Lines => _lines;

        /// <summary>Appelé sur le thread principal à chaque changement.</summary>
        public event Action? Changed;

        public ChatSession(BackendClient client, MainThreadDispatcher dispatcher)
        {
            _client = client;
            _dispatcher = dispatcher;
        }

        /// <summary>À appeler depuis le thread principal. Renvoie false si un envoi est déjà en cours.</summary>
        public bool Send(string question)
        {
            question = (question ?? "").Trim();
            if (question.Length == 0) return false;
            if (Interlocked.CompareExchange(ref _busy, 1, 0) != 0) return false;
            _lines.Add(new ChatLine(ChatRole.User, question));
            Changed?.Invoke();
            Task.Run(async () =>
            {
                ChatLine reply;
                try
                {
                    var a = await _client.AskAsync(question, ConversationId).ConfigureAwait(false);
                    ConversationId = a.ConversationId;
                    var meta = a.Route + (a.Provider != null ? " · " + a.Provider : "");
                    var text = a.Text;
                    if (a.Limitations.Length > 0) text += "\n⚠ " + string.Join("\n⚠ ", a.Limitations);
                    reply = new ChatLine(ChatRole.Director, text, meta);
                }
                catch (Exception ex)
                {
                    reply = new ChatLine(ChatRole.Error, ex.Message);
                }
                _dispatcher.Post(() =>
                {
                    _lines.Add(reply);
                    Volatile.Write(ref _busy, 0);
                    Changed?.Invoke();
                });
            });
            return true;
        }

        public void Reset()
        {
            ConversationId = null;
            _lines.Clear();
            Changed?.Invoke();
        }
    }
}
