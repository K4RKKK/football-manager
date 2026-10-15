using System.Drawing.Drawing2D;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace ClubDirector.Overlay;

/// <summary>
/// Panneau ClubDirector au-dessus de FM26 (le jeu doit être en « fenêtré sans bordure » ; un plein
/// écran exclusif passe devant toute fenêtre). Aucun lien avec le processus du jeu.
/// </summary>
public sealed class OverlayForm : Form
{
    private const int HotkeyId = 0xCD01;
    private const int ResizeGrip = 6;
    private static readonly Color Bg = Color.FromArgb(0x0B, 0x14, 0x1B);

    private readonly OverlaySettings _settings;
    private readonly WebView2 _web = new() { Dock = DockStyle.Fill, DefaultBackgroundColor = Bg };
    private readonly NotifyIcon _tray;
    private readonly System.Windows.Forms.Timer _retry = new() { Interval = 5000 };
    private readonly Uri _home;
    private bool _hotkeyOk;
    private bool _offline;
    private bool _showingOfflinePage;

    public OverlayForm(OverlaySettings settings)
    {
        _settings = settings;
        _home = new Uri(settings.Url);
        Text = "ClubDirector — Directeur sportif IA";
        FormBorderStyle = FormBorderStyle.None;
        TopMost = true;
        ShowInTaskbar = false;
        StartPosition = FormStartPosition.Manual;
        BackColor = Bg;
        Opacity = settings.Opacity;
        Padding = new Padding(settings.Side == "left" ? 0 : ResizeGrip, 0, settings.Side == "left" ? ResizeGrip : 0, 0);
        Controls.Add(_web);
        Icon = MakeIcon();

        var menu = new ContextMenuStrip();
        menu.Items.Add($"Afficher / masquer ({settings.Hotkey})", null, (_, _) => Toggle());
        menu.Items.Add("Recharger", null, (_, _) => GoHome());
        menu.Items.Add("Ouvrir les réglages (overlay.json)", null, (_, _) => OpenSettings());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Quitter", null, (_, _) => { _tray!.Visible = false; Application.Exit(); });
        _tray = new NotifyIcon { Icon = Icon, Text = "ClubDirector — Directeur sportif IA", ContextMenuStrip = menu, Visible = true };
        _tray.MouseClick += (_, e) => { if (e.Button == MouseButtons.Left) Toggle(); };

        _retry.Tick += (_, _) => { if (_offline) GoHome(); };
        PlaceOnScreen(Screen.FromPoint(Cursor.Position));
    }

    // ------------------------------------------------------------------ cycle de vie
    protected override async void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        try { _hotkeyOk = GlobalHotkey.Register(Handle, HotkeyId, _settings.Hotkey); }
        catch (FormatException) { _hotkeyOk = false; }
        if (!_hotkeyOk)
            _tray.ShowBalloonTip(6000, "ClubDirector", $"Raccourci « {_settings.Hotkey} » indisponible (déjà utilisé ?). Utilisez l'icône de la zone de notification ou modifiez overlay.json.", ToolTipIcon.Warning);
        await InitWebAsync();
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        if (_hotkeyOk) GlobalHotkey.Unregister(Handle, HotkeyId);
        _tray.Visible = false;
        _tray.Dispose();
        base.OnFormClosed(e);
    }

    protected override void WndProc(ref Message m)
    {
        const int WM_NCHITTEST = 0x84, HTLEFT = 10, HTRIGHT = 11;
        if (m.Msg == GlobalHotkey.WM_HOTKEY && m.WParam.ToInt32() == HotkeyId) { Toggle(); return; }
        if (m.Msg == WM_NCHITTEST)
        {
            // Bord intérieur de la fenêtre sans bordure : redimensionnement de la largeur.
            var p = PointToClient(new Point(unchecked((short)(long)m.LParam), unchecked((short)((long)m.LParam >> 16))));
            if (_settings.Side != "left" && p.X <= ResizeGrip) { m.Result = HTLEFT; return; }
            if (_settings.Side == "left" && p.X >= ClientSize.Width - ResizeGrip) { m.Result = HTRIGHT; return; }
        }
        base.WndProc(ref m);
    }

    protected override void OnResizeEnd(EventArgs e)
    {
        base.OnResizeEnd(e);
        _settings.Width = Width;
        _settings.Save();
    }

    // ------------------------------------------------------------------ affichage
    private void PlaceOnScreen(Screen screen)
    {
        var wa = screen.WorkingArea;
        var w = Math.Min(_settings.Width, wa.Width);
        Bounds = _settings.Side == "left"
            ? new Rectangle(wa.Left, wa.Top, w, wa.Height)
            : new Rectangle(wa.Right - w, wa.Top, w, wa.Height);
    }

    public void Toggle()
    {
        if (Visible && ContainsFocus) { HideOverlay(); return; }
        PlaceOnScreen(Screen.FromPoint(Cursor.Position));
        Show();
        TopMost = true;
        Activate();
        _web.Focus();
        Post("focus");
    }

    private void HideOverlay() => Hide();

    private void Post(string message)
    {
        try { _web.CoreWebView2?.PostWebMessageAsString(message); }
        catch (Exception) { /* page pas encore prête */ }
    }

    // ------------------------------------------------------------------ WebView2
    private async Task InitWebAsync()
    {
        try
        {
            var env = await CoreWebView2Environment.CreateAsync(null, Path.Combine(OverlaySettings.DataDir, "webview2"));
            await _web.EnsureCoreWebView2Async(env);
        }
        catch (Exception ex)
        {
            MessageBox.Show("WebView2 indisponible : " + ex.Message, "ClubDirector", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Application.Exit();
            return;
        }
        var core = _web.CoreWebView2;
        core.Settings.AreDefaultContextMenusEnabled = false;
        core.Settings.AreDevToolsEnabled = false;
        core.Settings.IsStatusBarEnabled = false;
        core.Settings.IsZoomControlEnabled = true;
        core.WebMessageReceived += (_, e) =>
        {
            var msg = e.TryGetWebMessageAsString();
            if (msg == "hide") BeginInvoke(HideOverlay);
        };
        // Seul le service local est affiché : toute autre navigation est refusée.
        core.NavigationStarting += (_, e) =>
        {
            if (Uri.TryCreate(e.Uri, UriKind.Absolute, out var u) && (u.Scheme == "data" || u.Scheme == "about")) return;
            if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out var target) || target.Host != _home.Host || target.Port != _home.Port)
                e.Cancel = true;
        };
        core.NewWindowRequested += (_, e) => e.Handled = true;
        core.NavigationCompleted += (_, e) =>
        {
            // La page d'attente (NavigateToString) est elle-même une navigation réussie : elle ne
            // doit pas faire croire que le service répond, sinon les nouvelles tentatives s'arrêtent.
            if (_showingOfflinePage) { _showingOfflinePage = false; return; }
            if (e.IsSuccess)
            {
                _offline = false;
                _retry.Stop();
                Post("hotkey:" + _settings.Hotkey);
                if (Visible) Post("focus");
            }
            else
            {
                // Chaque échec réaffiche la page d'attente (pas la page d'erreur de WebView2).
                _offline = true;
                _showingOfflinePage = true;
                _web.NavigateToString(OfflinePage());
                _retry.Start();
            }
        };
        GoHome();
        if (!_settings.StartHidden) Toggle();
    }

    private void GoHome()
    {
        try { _web.CoreWebView2?.Navigate(_home.ToString()); }
        catch (Exception) { /* nouvel essai au prochain tic */ }
    }

    private void OpenSettings()
    {
        _settings.Save();
        try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("notepad.exe", $"\"{OverlaySettings.FilePath}\"") { UseShellExecute = true }); }
        catch (Exception) { }
    }

    private string OfflinePage() => $$"""
        <!doctype html><html lang="fr"><meta charset="utf-8"><body style="margin:0;height:100vh;display:grid;place-items:center;
        background:#0B141B;color:#F2F6F8;font:14px/1.5 'Segoe UI',sans-serif;text-align:center">
        <div style="max-width:320px;padding:24px"><div style="font-size:15px;font-weight:600;margin-bottom:8px">Service ClubDirector non démarré</div>
        <div style="color:#9BAEB8">Lancez « Lancer ClubDirector.cmd ». Cette fenêtre se reconnecte toute seule
        à {{_home.GetLeftPart(UriPartial.Authority)}}.</div>
        <div style="color:#6F8590;font-size:12px;margin-top:14px">{{_settings.Hotkey}} : afficher / masquer</div></div></body></html>
        """;

    private static Icon MakeIcon()
    {
        using var bmp = new Bitmap(64, 64);
        using (var g = Graphics.FromImage(bmp))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.Clear(Color.Transparent);
            using var brush = new LinearGradientBrush(new Rectangle(0, 0, 64, 64), Color.FromArgb(0x3A, 0xD9, 0x8E), Color.FromArgb(0x16, 0x8A, 0x55), 45f);
            g.FillEllipse(brush, 2, 2, 60, 60);
            using var font = new Font("Segoe UI", 22, FontStyle.Bold, GraphicsUnit.Pixel);
            using var fg = new SolidBrush(Color.FromArgb(0x06, 0x12, 0x0C));
            var size = g.MeasureString("DS", font);
            g.DrawString("DS", font, fg, (64 - size.Width) / 2, (64 - size.Height) / 2);
        }
        return Icon.FromHandle(bmp.GetHicon());
    }
}
