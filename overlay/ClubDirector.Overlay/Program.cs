namespace ClubDirector.Overlay;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        // Une seule fenêtre ClubDirector à la fois.
        using var mutex = new Mutex(true, @"Local\ClubDirector.Overlay", out var first);
        if (!first) return;

        ApplicationConfiguration.Initialize();
        var settings = OverlaySettings.Load();
        var form = new OverlayForm(settings);
        // Le handle est créé tout de suite (raccourci global + WebView2) même si la fenêtre démarre masquée.
        _ = form.Handle;
        Application.Run();
        GC.KeepAlive(form);
    }
}
