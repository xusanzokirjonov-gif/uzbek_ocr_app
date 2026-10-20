import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

/// ════════════════════════════════════════════════════════════════════════════
///  iOS 26 SPATIAL GLASS DESIGN SYSTEM
///  Inspired by next-gen Apple Vision & iOS spatial glass aesthetics:
///   • Living bioluminescent aurora background
///   • Multi-layer frosted acrylic glass with specular highlights
///   • Dynamic Island status pill
///   • Holographic OCR viewfinder with animated laser sweep
///   • Liquid glass spring buttons with haptic feedback
/// ════════════════════════════════════════════════════════════════════════════

// ─── 1. Living Aurora Background ─────────────────────────────────────────────

class IOS26AuroraBackground extends StatefulWidget {
  final Widget child;
  final bool isDark;

  const IOS26AuroraBackground({
    super.key,
    required this.child,
    this.isDark = true,
  });

  @override
  State<IOS26AuroraBackground> createState() => _IOS26AuroraBackgroundState();
}

class _IOS26AuroraBackgroundState extends State<IOS26AuroraBackground>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 12),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = widget.isDark;

    return Stack(
      children: [
        // Base dark luxury / light crystal canvas
        Container(
          color: isDark ? const Color(0xFF070A14) : const Color(0xFFF3F5FA),
        ),

        // Animated Ambient Bioluminescent Orbs
        AnimatedBuilder(
          animation: _controller,
          builder: (context, _) {
            final val = _controller.value;
            return Stack(
              children: [
                // Orb 1: Electric Violet
                Positioned(
                  top: -80 + (val * 50),
                  left: -60 + (val * 40),
                  child: Container(
                    width: 340,
                    height: 340,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: RadialGradient(
                        colors: [
                          (isDark ? const Color(0xFF7928CA) : const Color(0xFF9D4EDD))
                              .withValues(alpha: isDark ? 0.38 : 0.22),
                          Colors.transparent,
                        ],
                      ),
                    ),
                  ),
                ),

                // Orb 2: Cyber Cyan
                Positioned(
                  top: 240 - (val * 60),
                  right: -90 + (val * 40),
                  child: Container(
                    width: 380,
                    height: 380,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: RadialGradient(
                        colors: [
                          (isDark ? const Color(0xFF00DFD8) : const Color(0xFF00B4D8))
                              .withValues(alpha: isDark ? 0.30 : 0.18),
                          Colors.transparent,
                        ],
                      ),
                    ),
                  ),
                ),

                // Orb 3: Quantum Indigo / Sunset Glow
                Positioned(
                  bottom: -60 + (val * 40),
                  left: 40 - (val * 30),
                  child: Container(
                    width: 360,
                    height: 360,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: RadialGradient(
                        colors: [
                          (isDark ? const Color(0xFF4361EE) : const Color(0xFF4895EF))
                              .withValues(alpha: isDark ? 0.32 : 0.18),
                          Colors.transparent,
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            );
          },
        ),

        // Foreground content
        widget.child,
      ],
    );
  }
}

// ─── 2. Spatial Glass Card ───────────────────────────────────────────────────

class IOS26GlassCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final EdgeInsetsGeometry? margin;
  final double borderRadius;
  final double blurSigma;
  final VoidCallback? onTap;
  final bool isDark;
  final Color? tintColor;
  final Border? customBorder;

  const IOS26GlassCard({
    super.key,
    required this.child,
    this.padding,
    this.margin,
    this.borderRadius = 24.0,
    this.blurSigma = 24.0,
    this.onTap,
    this.isDark = true,
    this.tintColor,
    this.customBorder,
  });

  @override
  Widget build(BuildContext context) {
    final bgAlpha = isDark ? 0.45 : 0.65;
    final baseBg = tintColor ?? (isDark ? const Color(0xFF13182C) : Colors.white);

    Widget card = Container(
      margin: margin,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(borderRadius),
        boxShadow: [
          BoxShadow(
            color: isDark
                ? Colors.black.withValues(alpha: 0.35)
                : const Color(0xFF6C63FF).withValues(alpha: 0.08),
            blurRadius: 28,
            offset: const Offset(0, 10),
            spreadRadius: -4,
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(borderRadius),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: blurSigma, sigmaY: blurSigma),
          child: Container(
            padding: padding ?? const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: baseBg.withValues(alpha: bgAlpha),
              borderRadius: BorderRadius.circular(borderRadius),
              border: customBorder ??
                  Border.all(
                    color: isDark
                        ? Colors.white.withValues(alpha: 0.16)
                        : Colors.white.withValues(alpha: 0.8),
                    width: 0.9,
                  ),
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: isDark
                    ? [
                        Colors.white.withValues(alpha: 0.12),
                        Colors.white.withValues(alpha: 0.02),
                      ]
                    : [
                        Colors.white.withValues(alpha: 0.90),
                        Colors.white.withValues(alpha: 0.40),
                      ],
              ),
            ),
            child: child,
          ),
        ),
      ),
    );

    if (onTap != null) {
      return GestureDetector(
        onTap: () {
          HapticFeedback.lightImpact();
          onTap!();
        },
        child: card,
      );
    }
    return card;
  }
}

// ─── 3. iOS 26 Dynamic Island Status Capsule ────────────────────────────────

class IOS26DynamicIsland extends StatefulWidget {
  final String text;
  final String? subtext;
  final IconData icon;
  final Color statusColor;
  final bool isLive;
  final bool isPulsing;
  final VoidCallback? onTap;
  final bool isDark;

  const IOS26DynamicIsland({
    super.key,
    required this.text,
    this.subtext,
    required this.icon,
    this.statusColor = const Color(0xFF00F5D4),
    this.isLive = true,
    this.isPulsing = false,
    this.onTap,
    this.isDark = true,
  });

  @override
  State<IOS26DynamicIsland> createState() => _IOS26DynamicIslandState();
}

class _IOS26DynamicIslandState extends State<IOS26DynamicIsland>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.selectionClick();
        widget.onTap?.call();
      },
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(32),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 30, sigmaY: 30),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: widget.isDark
                    ? const Color(0xFF0B0E1B).withValues(alpha: 0.82)
                    : Colors.white.withValues(alpha: 0.85),
                borderRadius: BorderRadius.circular(32),
                border: Border.all(
                  color: widget.statusColor.withValues(alpha: 0.35),
                  width: 0.9,
                ),
                boxShadow: [
                  BoxShadow(
                    color: widget.statusColor.withValues(alpha: 0.18),
                    blurRadius: 16,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Pulsing Live Indicator Beacon
                  AnimatedBuilder(
                    animation: _pulseController,
                    builder: (context, _) {
                      final scale = 0.85 + (_pulseController.value * 0.35);
                      return Transform.scale(
                        scale: widget.isPulsing ? scale : 1.0,
                        child: Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: widget.statusColor,
                            boxShadow: [
                              BoxShadow(
                                color: widget.statusColor.withValues(alpha: 0.8),
                                blurRadius: 8,
                                spreadRadius: 1,
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                  const SizedBox(width: 9),

                  // Icon
                  Icon(
                    widget.icon,
                    size: 14,
                    color: widget.isDark ? Colors.white70 : const Color(0xFF1E2235),
                  ),
                  const SizedBox(width: 7),

                  // Title Text
                  Flexible(
                    child: Text(
                      widget.text,
                      overflow: TextOverflow.ellipsis,
                      style: GoogleFonts.inter(
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700,
                        letterSpacing: -0.2,
                        color: widget.isDark ? Colors.white : const Color(0xFF111425),
                      ),
                    ),
                  ),

                  if (widget.subtext != null) ...[
                    const SizedBox(width: 5),
                    Text(
                      widget.subtext!,
                      style: GoogleFonts.inter(
                        fontSize: 11,
                        fontWeight: FontWeight.w500,
                        color: widget.statusColor,
                      ),
                    ),
                  ],

                  const SizedBox(width: 5),
                  Icon(
                    Icons.arrow_forward_ios_rounded,
                    size: 10,
                    color: widget.isDark ? Colors.white38 : Colors.black38,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ─── 4. Holographic OCR Scanner Viewport ─────────────────────────────────────

class IOS26HoloScanner extends StatefulWidget {
  final VoidCallback onCameraTap;
  final VoidCallback onGalleryTap;
  final bool isDark;
  final String title;
  final String subtitle;

  const IOS26HoloScanner({
    super.key,
    required this.onCameraTap,
    required this.onGalleryTap,
    this.isDark = true,
    required this.title,
    required this.subtitle,
  });

  @override
  State<IOS26HoloScanner> createState() => _IOS26HoloScannerState();
}

class _IOS26HoloScannerState extends State<IOS26HoloScanner>
    with SingleTickerProviderStateMixin {
  late final AnimationController _scanController;

  @override
  void initState() {
    super.initState();
    _scanController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2600),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _scanController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = widget.isDark;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(32),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 30, sigmaY: 30),
          child: Container(
            height: 250,
            decoration: BoxDecoration(
              color: isDark
                  ? const Color(0xFF0F1426).withValues(alpha: 0.6)
                  : Colors.white.withValues(alpha: 0.7),
              borderRadius: BorderRadius.circular(32),
              border: Border.all(
                color: isDark
                    ? Colors.white.withValues(alpha: 0.16)
                    : Colors.white.withValues(alpha: 0.9),
                width: 1,
              ),
              boxShadow: [
                BoxShadow(
                  color: isDark
                      ? const Color(0xFF6C63FF).withValues(alpha: 0.15)
                      : const Color(0xFF6C63FF).withValues(alpha: 0.1),
                  blurRadius: 32,
                  spreadRadius: -4,
                ),
              ],
            ),
            child: Stack(
              children: [
                // Subtle holographic grid lines
                Positioned.fill(
                  child: CustomPaint(
                    painter: _HoloGridPainter(isDark: isDark),
                  ),
                ),

                // Corner Reticle Brackets (HUD style)
                Positioned(
                  top: 18,
                  left: 18,
                  child: _buildCornerReticle(isTop: true, isLeft: true),
                ),
                Positioned(
                  top: 18,
                  right: 18,
                  child: _buildCornerReticle(isTop: true, isLeft: false),
                ),
                Positioned(
                  bottom: 18,
                  left: 18,
                  child: _buildCornerReticle(isTop: false, isLeft: true),
                ),
                Positioned(
                  bottom: 18,
                  right: 18,
                  child: _buildCornerReticle(isTop: false, isLeft: false),
                ),

                // Animated Sweeping Laser Line
                AnimatedBuilder(
                  animation: _scanController,
                  builder: (context, _) {
                    final topOffset = 25 + (_scanController.value * 195);
                    return Positioned(
                      top: topOffset,
                      left: 24,
                      right: 24,
                      child: Container(
                        height: 2,
                        decoration: BoxDecoration(
                          gradient: const LinearGradient(
                            colors: [
                              Colors.transparent,
                              Color(0xFF00F5D4),
                              Color(0xFF7928CA),
                              Color(0xFF00F5D4),
                              Colors.transparent,
                            ],
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFF00F5D4).withValues(alpha: 0.9),
                              blurRadius: 10,
                              spreadRadius: 1.5,
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),

                // Center Holographic Content & Interactive Target
                Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // Spatial Lens Icon
                      GestureDetector(
                        onTap: () {
                          HapticFeedback.mediumImpact();
                          widget.onCameraTap();
                        },
                        child: Container(
                          width: 76,
                          height: 76,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            gradient: const LinearGradient(
                              begin: Alignment.topLeft,
                              end: Alignment.bottomRight,
                              colors: [Color(0xFF7928CA), Color(0xFF00DFD8)],
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: const Color(0xFF7928CA).withValues(alpha: 0.5),
                                blurRadius: 28,
                                spreadRadius: 2,
                              ),
                            ],
                          ),
                          child: const Icon(
                            Icons.center_focus_strong_rounded,
                            size: 38,
                            color: Colors.white,
                          ),
                        ),
                      ),
                      const SizedBox(height: 14),

                      // Title
                      Text(
                        widget.title,
                        style: GoogleFonts.inter(
                          fontSize: 18,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.4,
                          color: isDark ? Colors.white : const Color(0xFF141727),
                        ),
                      ),
                      const SizedBox(height: 4),

                      // Spatial Badge
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: isDark
                              ? Colors.white.withValues(alpha: 0.08)
                              : Colors.black.withValues(alpha: 0.06),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          widget.subtitle,
                          style: GoogleFonts.inter(
                            fontSize: 11.5,
                            fontWeight: FontWeight.w600,
                            color: isDark ? const Color(0xFF00F5D4) : const Color(0xFF6C63FF),
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCornerReticle({required bool isTop, required bool isLeft}) {
    return Container(
      width: 22,
      height: 22,
      decoration: BoxDecoration(
        border: Border(
          top: isTop
              ? const BorderSide(color: Color(0xFF00F5D4), width: 2.5)
              : BorderSide.none,
          bottom: !isTop
              ? const BorderSide(color: Color(0xFF00F5D4), width: 2.5)
              : BorderSide.none,
          left: isLeft
              ? const BorderSide(color: Color(0xFF00F5D4), width: 2.5)
              : BorderSide.none,
          right: !isLeft
              ? const BorderSide(color: Color(0xFF00F5D4), width: 2.5)
              : BorderSide.none,
        ),
      ),
    );
  }
}

class _HoloGridPainter extends CustomPainter {
  final bool isDark;
  _HoloGridPainter({required this.isDark});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = isDark
          ? Colors.white.withValues(alpha: 0.04)
          : Colors.black.withValues(alpha: 0.03)
      ..strokeWidth = 0.8;

    const step = 32.0;
    for (double x = 0; x < size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (double y = 0; y < size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// ─── 5. Liquid Glass Spring Button ──────────────────────────────────────────

class IOS26LiquidButton extends StatefulWidget {
  final IconData icon;
  final String label;
  final String subtitle;
  final List<Color> gradientColors;
  final VoidCallback onTap;
  final bool isDark;

  const IOS26LiquidButton({
    super.key,
    required this.icon,
    required this.label,
    required this.subtitle,
    required this.gradientColors,
    required this.onTap,
    this.isDark = true,
  });

  @override
  State<IOS26LiquidButton> createState() => _IOS26LiquidButtonState();
}

class _IOS26LiquidButtonState extends State<IOS26LiquidButton> {
  bool _isPressed = false;

  @override
  Widget build(BuildContext context) {
    final isDark = widget.isDark;

    return GestureDetector(
      onTapDown: (_) => setState(() => _isPressed = true),
      onTapUp: (_) {
        setState(() => _isPressed = false);
        HapticFeedback.lightImpact();
        widget.onTap();
      },
      onTapCancel: () => setState(() => _isPressed = false),
      child: AnimatedScale(
        scale: _isPressed ? 0.965 : 1.0,
        duration: const Duration(milliseconds: 140),
        curve: Curves.easeOutBack,
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 7),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(24),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
                decoration: BoxDecoration(
                  color: isDark
                      ? const Color(0xFF14192D).withValues(alpha: 0.55)
                      : Colors.white.withValues(alpha: 0.75),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(
                    color: isDark
                        ? Colors.white.withValues(alpha: 0.14)
                        : Colors.white.withValues(alpha: 0.8),
                    width: 0.9,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: widget.gradientColors.first.withValues(alpha: isDark ? 0.14 : 0.08),
                      blurRadius: 20,
                      offset: const Offset(0, 6),
                    ),
                  ],
                ),
                child: Row(
                  children: [
                    // Dynamic Glass Icon Shield
                    Container(
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(16),
                        gradient: LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: widget.gradientColors,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: widget.gradientColors.first.withValues(alpha: 0.45),
                            blurRadius: 14,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: Icon(widget.icon, color: Colors.white, size: 24),
                    ),
                    const SizedBox(width: 16),

                    // Labels
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            widget.label,
                            style: GoogleFonts.inter(
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                              letterSpacing: -0.3,
                              color: isDark ? Colors.white : const Color(0xFF151829),
                            ),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            widget.subtitle,
                            style: GoogleFonts.inter(
                              fontSize: 12.5,
                              color: isDark ? Colors.white60 : const Color(0xFF6B7280),
                            ),
                          ),
                        ],
                      ),
                    ),

                    // Trailing glowing arrow capsule
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: isDark
                            ? Colors.white.withValues(alpha: 0.07)
                            : Colors.black.withValues(alpha: 0.04),
                      ),
                      child: Icon(
                        Icons.arrow_forward_ios_rounded,
                        size: 13,
                        color: isDark ? Colors.white54 : Colors.black45,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ─── 6. iOS 26 Glass App Bar ────────────────────────────────────────────────

class IOS26GlassAppBar extends StatelessWidget {
  final String title;
  final Widget? leading;
  final List<Widget>? actions;
  final bool isDark;

  const IOS26GlassAppBar({
    super.key,
    required this.title,
    this.leading,
    this.actions,
    this.isDark = true,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          if (leading != null)
            leading!
          else
            Row(
              children: [
                // Glowing Apple-style Iris logo mark
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(10),
                    gradient: const LinearGradient(
                      colors: [Color(0xFF7928CA), Color(0xFF00DFD8)],
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF7928CA).withValues(alpha: 0.4),
                        blurRadius: 12,
                      ),
                    ],
                  ),
                  child: const Icon(
                    Icons.document_scanner_rounded,
                    color: Colors.white,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 12),
                Text(
                  title,
                  style: GoogleFonts.inter(
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.6,
                    color: isDark ? Colors.white : const Color(0xFF111425),
                  ),
                ),
              ],
            ),
          if (actions != null)
            Row(
              mainAxisSize: MainAxisSize.min,
              children: actions!,
            ),
        ],
      ),
    );
  }
}
