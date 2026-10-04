"""Orbe central animado do N.E.X.U.S.

Desenha aneis rotativos ciberneticos, marcas de mira, brilho radial e ondulacao
de audio em tempo real usando QPainter.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
import math
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QSize
from PySide6.QtGui import QPainter, QRadialGradient, QColor, QPen, QFont, QPolygonF
from PySide6.QtWidgets import QWidget


class Orbe(QWidget):
    """Widget de visualizacao central com orbe cibernetico e reatividade de audio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 280)

        # Angulos e fases dos aneis e ondas
        self._angulo_anel1 = 0.0
        self._angulo_anel2 = 0.0
        self._angulo_anel3 = 0.0
        self._pulso = 0.0
        self._fase_onda = 0.0

        # Controle de nivel de audio e suavizacao
        self._nivel_alvo = 0.0
        self._nivel_suavizado = 0.0
        self._peso_suavizacao = 0.82

        # Timer de animacao a ~30 FPS (33 ms)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._atualizar_animacao)
        self._timer.start()

    def sizeHint(self) -> QSize:
        return QSize(320, 320)

    def set_nivel(self, valor: float) -> None:
        """Define o nivel de atividade de fala (0.0 a 1.0) para modular a ondulacao."""
        try:
            self._nivel_alvo = max(0.0, min(1.0, float(valor)))
        except (ValueError, TypeError):
            self._nivel_alvo = 0.0

    def _atualizar_animacao(self) -> None:
        """Avanca os angulos de rotacao e aplica media movel no nivel."""
        # Rotacoes dos aneis em velocidades e sentidos diferentes
        self._angulo_anel1 = (self._angulo_anel1 + 1.2) % 360.0
        self._angulo_anel2 = (self._angulo_anel2 - 0.8) % 360.0
        self._angulo_anel3 = (self._angulo_anel3 + 2.0) % 360.0

        # Pulso respiratorio e fase de propagacao da onda
        self._pulso = (self._pulso + 0.06) % (2.0 * math.pi)
        self._fase_onda = (self._fase_onda + 0.18) % (2.0 * math.pi)

        # Suavizacao por media movel exponencial para evitar tremores
        self._nivel_suavizado = (
            self._nivel_suavizado * self._peso_suavizacao
            + self._nivel_alvo * (1.0 - self._peso_suavizacao)
        )
        if self._nivel_suavizado < 0.003 and self._nivel_alvo == 0.0:
            self._nivel_suavizado = 0.0

        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        largura = self.width()
        altura = self.height()
        cx = largura / 2.0
        cy = altura / 2.0
        r_base = min(largura, altura) * 0.42

        # 1. Brilho radial central
        brilho_alfa = int(45 + 15 * math.sin(self._pulso) + 40 * self._nivel_suavizado)
        gradiente = QRadialGradient(cx, cy, r_base * 0.85)
        gradiente.setColorAt(0.0, QColor(0, 229, 255, min(255, brilho_alfa)))
        gradiente.setColorAt(0.45, QColor(0, 131, 143, int(brilho_alfa * 0.4)))
        gradiente.setColorAt(1.0, QColor(4, 18, 26, 0))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradiente)
        painter.drawEllipse(QPointF(cx, cy), r_base * 0.85, r_base * 0.85)

        # 2. Borda externa com ondulacao de audio ou lisa em silencio
        r_ext = r_base * 0.96
        if self._nivel_suavizado > 0.005:
            # Ondulacao harmonica proporcional ao nivel de fala
            pontos = []
            num_passos = 180
            amp = r_base * 0.09 * self._nivel_suavizado
            for i in range(num_passos):
                theta = (i / num_passos) * 2.0 * math.pi
                ond = (
                    math.sin(6.0 * theta + self._fase_onda) * 0.65
                    + math.sin(12.0 * theta - self._fase_onda * 1.4) * 0.35
                )
                r_atual = r_ext + amp * ond
                px = cx + r_atual * math.cos(theta)
                py = cy + r_atual * math.sin(theta)
                pontos.append(QPointF(px, py))

            caneta_onda = QPen(
                QColor(0, 229, 255, int(150 + 105 * self._nivel_suavizado)),
                1.6,
            )
            painter.setPen(caneta_onda)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(QPolygonF(pontos))
        else:
            # Borda lisa em repouso
            caneta_lisa = QPen(QColor(0, 229, 255, 110), 1.2)
            painter.setPen(caneta_lisa)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), r_ext, r_ext)

        # 3. Marcas de graduacao e mira em volta
        r_marca_ini = r_base * 0.90
        for grau in range(0, 360, 10):
            rad = math.radians(grau)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            if grau % 30 == 0:
                tam = r_base * 0.05
                alfa = 180
                espessura = 1.4
            else:
                tam = r_base * 0.025
                alfa = 90
                espessura = 1.0

            painter.setPen(QPen(QColor(0, 229, 255, alfa), espessura))
            p1 = QPointF(cx + r_marca_ini * cos_a, cy + r_marca_ini * sin_a)
            p2 = QPointF(cx + (r_marca_ini + tam) * cos_a, cy + (r_marca_ini + tam) * sin_a)
            painter.drawLine(p1, p2)

        # Miras cardinais (0, 90, 180, 270)
        painter.setPen(QPen(QColor(0, 229, 255, 220), 1.8))
        mira_dist = r_base * 1.02
        mira_tam = r_base * 0.06
        for angulo in (0, 90, 180, 270):
            rad = math.radians(angulo)
            p1 = QPointF(cx + mira_dist * math.cos(rad), cy + mira_dist * math.sin(rad))
            p2 = QPointF(
                cx + (mira_dist + mira_tam) * math.cos(rad),
                cy + (mira_dist + mira_tam) * math.sin(rad),
            )
            painter.drawLine(p1, p2)

        # 4. Aneis em arco girando em velocidades e sentidos diferentes
        # Anel 1 (externo, sentido horario)
        r_anel1 = r_base * 0.82
        rect_anel1 = QRectF(cx - r_anel1, cy - r_anel1, r_anel1 * 2, r_anel1 * 2)
        painter.setPen(QPen(QColor(0, 229, 255, 170), 2.0))
        for i in range(3):
            inicio_16 = int((self._angulo_anel1 + i * 120.0) * 16)
            arco_16 = int(65 * 16)
            painter.drawArc(rect_anel1, inicio_16, arco_16)

        # Anel 2 (intermediario, sentido anti-horario)
        r_anel2 = r_base * 0.69
        rect_anel2 = QRectF(cx - r_anel2, cy - r_anel2, r_anel2 * 2, r_anel2 * 2)
        painter.setPen(QPen(QColor(128, 243, 255, 210), 2.4))
        for i in range(4):
            inicio_16 = int((self._angulo_anel2 + i * 90.0) * 16)
            arco_16 = int(45 * 16)
            painter.drawArc(rect_anel2, inicio_16, arco_16)

        # Anel 3 (interno rapido, sentido horario)
        r_anel3 = r_base * 0.55
        rect_anel3 = QRectF(cx - r_anel3, cy - r_anel3, r_anel3 * 2, r_anel3 * 2)
        painter.setPen(QPen(QColor(0, 229, 255, 140), 1.6))
        for i in range(2):
            inicio_16 = int((self._angulo_anel3 + i * 180.0) * 16)
            arco_16 = int(80 * 16)
            painter.drawArc(rect_anel3, inicio_16, arco_16)

        # Anel 4 (circulo pontilhado sutil)
        r_anel4 = r_base * 0.44
        rect_anel4 = QRectF(cx - r_anel4, cy - r_anel4, r_anel4 * 2, r_anel4 * 2)
        painter.setPen(QPen(QColor(0, 229, 255, 80), 1.0, Qt.PenStyle.DashLine))
        painter.drawEllipse(rect_anel4)

        # 5. Texto central "N.E.X.U.S." com espacamento
        font_titulo = QFont("Consolas", 18, QFont.Weight.Bold)
        font_titulo.setStyleHint(QFont.StyleHint.Monospace)
        font_titulo.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 5.0)

        painter.setFont(font_titulo)
        painter.setPen(QPen(QColor(224, 247, 250, 240)))
        rect_titulo = QRectF(cx - 150, cy - 22, 300, 32)
        painter.drawText(rect_titulo, Qt.AlignmentFlag.AlignCenter, "N.E.X.U.S.")

        # Subtitulo "NEURAL EXECUTION & USER SYSTEM"
        font_sub = QFont("Consolas", 6, QFont.Weight.DemiBold)
        font_sub.setStyleHint(QFont.StyleHint.Monospace)
        font_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)

        painter.setFont(font_sub)
        painter.setPen(QPen(QColor(0, 229, 255, 185)))
        rect_sub = QRectF(cx - 160, cy + 14, 320, 18)
        painter.drawText(rect_sub, Qt.AlignmentFlag.AlignCenter, "NEURAL EXECUTION & USER SYSTEM")
