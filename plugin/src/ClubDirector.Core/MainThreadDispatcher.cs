using System;
using System.Collections.Concurrent;
using System.Diagnostics;

namespace ClubDirector.Core
{
    /// <summary>
    /// File d'actions à exécuter sur le thread principal d'Unity (seul autorisé à toucher l'UI).
    /// Les threads de travail y déposent des actions courtes ; Update() les draine avec un budget
    /// de temps par image pour ne jamais faire chuter les FPS de FM26.
    /// </summary>
    public sealed class MainThreadDispatcher
    {
        private readonly ConcurrentQueue<Action> _queue = new();
        private readonly Action<Exception>? _onError;

        public MainThreadDispatcher(Action<Exception>? onError = null) => _onError = onError;

        public int Pending => _queue.Count;

        public void Post(Action action)
        {
            if (action == null) throw new ArgumentNullException(nameof(action));
            _queue.Enqueue(action);
        }

        /// <summary>Exécute des actions jusqu'à épuisement du budget. Une exception n'interrompt pas la file.</summary>
        public int Drain(TimeSpan budget, int maxActions = 64)
        {
            var sw = Stopwatch.StartNew();
            int done = 0;
            while (done < maxActions && sw.Elapsed < budget && _queue.TryDequeue(out var action))
            {
                done++;
                try { action(); }
                catch (Exception ex) { _onError?.Invoke(ex); }
            }
            return done;
        }
    }
}
