namespace ClubDirector.Overlay;

/// <summary>Géométrie de la fenêtre « téléphone » (testable hors interface).</summary>
public static class PhoneLayout
{
    /// <summary>Proportions de l'iPhone affiché par la page (cadre compris), en pixels logiques.</summary>
    public const double Ratio = 414.0 / 860.0;
    /// <summary>Rayon des coins du cadre (identique au CSS de la page).</summary>
    public const int CornerRadius = 56;
    private const int Margin = 24;

    /// <summary>Rectangle de la fenêtre : hauteur demandée (bornée à l'écran), position enregistrée si elle est
    /// visible sur cet écran, sinon à droite et centré verticalement.</summary>
    public static Rectangle Compute(Rectangle workArea, int phoneHeight, double scale, Point? saved)
    {
        var h = (int)Math.Round(Math.Min(phoneHeight * scale, workArea.Height - 16));
        var w = (int)Math.Round(h * Ratio);
        if (saved is { } p)
        {
            var r = new Rectangle(p.X, p.Y, w, h);
            if (workArea.Contains(new Point(r.Left + w / 2, r.Top + 20)))
            {
                r.X = Math.Clamp(r.X, workArea.Left - w / 2, workArea.Right - w / 2);
                r.Y = Math.Clamp(r.Y, workArea.Top, workArea.Bottom - h);
                return r;
            }
        }
        return new Rectangle(workArea.Right - w - Margin, workArea.Top + (workArea.Height - h) / 2, w, h);
    }
}
