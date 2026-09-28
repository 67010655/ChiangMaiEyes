from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "fire-to-policy-geoai-proposal-th.pdf"
FONT_REGULAR = Path(r"C:\Windows\Fonts\tahoma.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\tahomabd.ttf")


PAGE_W, PAGE_H = A4
MARGIN_X = 46
TOP = PAGE_H - 42
BOTTOM = 44
CONTENT_W = PAGE_W - (MARGIN_X * 2)

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#51606d")
GREEN = colors.HexColor("#1f6f5b")
TEAL = colors.HexColor("#2f8f9d")
AMBER = colors.HexColor("#b7791f")
LIGHT = colors.HexColor("#eef6f3")
LINE = colors.HexColor("#d6e3df")


def setup_fonts():
    pdfmetrics.registerFont(TTFont("Thai", str(FONT_REGULAR)))
    pdfmetrics.registerFont(TTFont("Thai-Bold", str(FONT_BOLD)))


def wrap_text(text, font_name, font_size, max_width):
    lines = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            lines.append("")
            continue
        words = raw.split(" ")
        line = ""
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            current = ""
            for char in word:
                candidate_char = current + char
                if pdfmetrics.stringWidth(candidate_char, font_name, font_size) <= max_width:
                    current = candidate_char
                else:
                    if current:
                        lines.append(current)
                    current = char
            line = current
        if line:
            lines.append(line)
    return lines


class ProposalPDF:
    def __init__(self):
        setup_fonts()
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        self.c = canvas.Canvas(str(OUTPUT), pagesize=A4)
        self.page = 1
        self.y = TOP

    def save(self):
        self.footer()
        self.c.save()

    def footer(self):
        self.c.setStrokeColor(LINE)
        self.c.line(MARGIN_X, 32, PAGE_W - MARGIN_X, 32)
        self.c.setFillColor(MUTED)
        self.c.setFont("Thai", 8.5)
        self.c.drawString(MARGIN_X, 20, "GeoHackathon 2026 Proposal - Fire-to-Policy GeoAI")
        self.c.drawRightString(PAGE_W - MARGIN_X, 20, f"Page {self.page}")

    def new_page(self):
        self.footer()
        self.c.showPage()
        self.page += 1
        self.y = TOP

    def ensure(self, height):
        if self.y - height < BOTTOM:
            self.new_page()

    def title_page(self):
        self.c.setFillColor(GREEN)
        self.c.roundRect(MARGIN_X, PAGE_H - 112, CONTENT_W, 70, 8, fill=1, stroke=0)
        self.c.setFillColor(colors.white)
        self.c.setFont("Thai-Bold", 18)
        self.c.drawString(MARGIN_X + 18, PAGE_H - 76, "Fire-to-Policy GeoAI")
        self.c.setFont("Thai", 12.5)
        self.c.drawString(MARGIN_X + 18, PAGE_H - 96, "ระบบภูมิสารสนเทศอัจฉริยะเพื่อแปลงข้อมูลไฟป่าและหมอกควันสู่แผนปฏิบัติการท้องถิ่น")
        self.y = PAGE_H - 138

        self.badge("Challenge Domain", "Flood risk and disaster preparedness: ความเสี่ยงอุทกภัยและการเตรียมความพร้อมรับมือภัยพิบัติ")
        self.badge("Pilot Foundation", "ต่อยอดจาก ChiangMaiEyes เป็นพื้นที่นำร่องเชียงใหม่ และขยายเป็นกรอบการทำงานสำหรับภาคเหนือ")
        self.section("บทสรุปโครงการ", amber=True)
        self.paragraph(
            "โครงการ Fire-to-Policy GeoAI เสนอระบบ GeoAI ที่เปลี่ยนข้อมูลจุดความร้อน ภาพถ่ายดาวเทียม "
            "ข้อมูลฝน สภาพอากาศ ภูมิประเทศ ขอบเขตป่า ป่าชุมชน และขอบเขตการปกครอง ให้กลายเป็นข้อมูลข่าวกรองเชิงนโยบาย "
            "สำหรับการจัดการไฟป่า หมอกควัน และ PM2.5 ในภาคเหนือของประเทศไทย"
        )
        self.paragraph(
            "แนวคิดนี้ต่อยอดจากต้นแบบ ChiangMaiEyes ที่เคยพัฒนาเพื่อมองปัญหาไฟป่าและหมอกควันในจังหวัดเชียงใหม่ "
            "แต่ข้อเสนอครั้งนี้ขยายมุมมองจากแดชบอร์ดติดตามสถานการณ์ ไปสู่ระบบที่ตอบคำถามเชิงปฏิบัติได้ว่า "
            "พื้นที่ใดควรถูกจัดการก่อน ใครเป็นผู้รับผิดชอบ ปัจจัยเสี่ยงคืออะไร และผลการดำเนินงานของแต่ละพื้นที่เปลี่ยนแปลงอย่างไรในแต่ละสัปดาห์"
        )
        self.callout(
            "เป้าหมายหลัก",
            "จาก pixel สู่ policy action: ไม่ใช่เพียงแสดงจุดความร้อนบนแผนที่ แต่แปลงข้อมูลดาวเทียมและบริบทพื้นที่ให้เป็นลำดับความสำคัญ แผนเฝ้าระวัง และข้อมูลสนับสนุนการตัดสินใจของหน่วยงานท้องถิ่น"
        )

    def badge(self, label, value):
        self.ensure(38)
        self.c.setFillColor(LIGHT)
        self.c.roundRect(MARGIN_X, self.y - 31, CONTENT_W, 31, 5, fill=1, stroke=0)
        self.c.setFillColor(GREEN)
        self.c.setFont("Thai-Bold", 9)
        self.c.drawString(MARGIN_X + 12, self.y - 12, label)
        self.c.setFillColor(INK)
        self.c.setFont("Thai", 9.5)
        self.c.drawString(MARGIN_X + 112, self.y - 12, value[:115])
        self.y -= 42

    def section(self, title, amber=False):
        self.ensure(34)
        color = AMBER if amber else TEAL
        self.c.setFillColor(color)
        self.c.roundRect(MARGIN_X, self.y - 24, 6, 20, 2, fill=1, stroke=0)
        self.c.setFillColor(INK)
        self.c.setFont("Thai-Bold", 13.5)
        self.c.drawString(MARGIN_X + 14, self.y - 18, title)
        self.y -= 32

    def paragraph(self, text, size=10.4, leading=15):
        lines = wrap_text(text, "Thai", size, CONTENT_W)
        self.ensure(len(lines) * leading + 8)
        self.c.setFillColor(INK)
        self.c.setFont("Thai", size)
        for line in lines:
            self.c.drawString(MARGIN_X, self.y, line)
            self.y -= leading
        self.y -= 5

    def bullet(self, items):
        for item in items:
            lines = wrap_text(item, "Thai", 10.2, CONTENT_W - 18)
            self.ensure(len(lines) * 14 + 4)
            self.c.setFillColor(GREEN)
            self.c.circle(MARGIN_X + 4, self.y + 3, 2.2, fill=1, stroke=0)
            self.c.setFillColor(INK)
            self.c.setFont("Thai", 10.2)
            for i, line in enumerate(lines):
                self.c.drawString(MARGIN_X + 18, self.y, line)
                self.y -= 14
            self.y -= 3

    def callout(self, title, body):
        lines = wrap_text(body, "Thai", 10.1, CONTENT_W - 24)
        h = 34 + len(lines) * 14
        self.ensure(h + 8)
        self.c.setFillColor(colors.HexColor("#fff8e8"))
        self.c.setStrokeColor(colors.HexColor("#ead7ad"))
        self.c.roundRect(MARGIN_X, self.y - h, CONTENT_W, h, 7, fill=1, stroke=1)
        self.c.setFillColor(AMBER)
        self.c.setFont("Thai-Bold", 10.8)
        self.c.drawString(MARGIN_X + 12, self.y - 18, title)
        self.c.setFillColor(INK)
        self.c.setFont("Thai", 10.1)
        yy = self.y - 36
        for line in lines:
            self.c.drawString(MARGIN_X + 12, yy, line)
            yy -= 14
        self.y -= h + 14


def build():
    pdf = ProposalPDF()
    pdf.title_page()

    pdf.section("1. ความชัดเจนของปัญหาและความสำคัญต่อบริบทไทย")
    pdf.paragraph(
        "ภาคเหนือของประเทศไทยเผชิญปัญหาไฟป่า การเผาในที่โล่ง และฝุ่น PM2.5 ซ้ำทุกปี โดยเฉพาะจังหวัดเชียงใหม่และพื้นที่ใกล้เคียง "
        "แม้ปัจจุบันจะมีข้อมูลจุดความร้อนจากดาวเทียม ข้อมูลสภาพอากาศ และข้อมูลพื้นที่ป่าให้ใช้งานมากขึ้น "
        "แต่ข้อมูลเหล่านี้มักถูกใช้เป็นเพียงข้อมูลติดตามสถานการณ์ มากกว่าการแปลงเป็นข้อมูลเพื่อการตัดสินใจเชิงปฏิบัติ"
    )
    pdf.paragraph(
        "ปัญหาสำคัญคือหน่วยงานท้องถิ่นยังตอบคำถามเชิงนโยบายได้ยาก เช่น พื้นที่ใดควรถูกเฝ้าระวังก่อนในสัปดาห์นี้ "
        "พื้นที่ใดมีความเสี่ยงซ้ำซาก ใครเป็นหน่วยงานหรือพื้นที่รับผิดชอบ ชุมชนหรือป่าชุมชนใดได้รับผลกระทบ "
        "และจะติดตามผลการป้องกันไฟในแต่ละพื้นที่อย่างไร"
    )
    pdf.paragraph(
        "ปัญหานี้มีความสำคัญต่อประเทศไทยเพราะไฟป่าและหมอกควันไม่ได้เป็นเพียงปัญหาสิ่งแวดล้อม แต่เกี่ยวข้องกับสุขภาพประชาชน "
        "เศรษฐกิจท้องถิ่น การท่องเที่ยว เกษตรกรรม การอนุรักษ์ป่า และการประสานงานระหว่างหน่วยงานหลายระดับ"
    )
    pdf.bullet([
        "ผู้ได้รับประโยชน์หลัก: ศูนย์บัญชาการระดับจังหวัดและอำเภอ องค์กรปกครองส่วนท้องถิ่น หน่วยงานป่าไม้ คณะกรรมการป่าชุมชน หน่วยงานสาธารณสุข และประชาชนในพื้นที่เสี่ยง",
        "พื้นที่นำร่อง: จังหวัดเชียงใหม่ โดยใช้ประสบการณ์จาก ChiangMaiEyes เป็นฐานข้อมูลและต้นแบบการออกแบบระบบ",
        "มุมมองใหม่: ขยายจากการดูสถานการณ์บนแผนที่ ไปสู่ระบบจัดลำดับพื้นที่เสี่ยงและสร้างข้อเสนอเชิงปฏิบัติรายสัปดาห์"
    ])

    pdf.section("2. แนวทาง GeoAI และวิธีดำเนินงาน")
    pdf.paragraph(
        "โครงการนี้เสนอแนวทาง GeoAI ที่ผสานข้อมูลภูมิสารสนเทศ ข้อมูลดาวเทียม และการวิเคราะห์เชิงพื้นที่ "
        "เพื่อเปลี่ยนข้อมูลไฟป่าและหมอกควันให้เป็นข้อมูลข่าวกรองเชิงนโยบายสำหรับท้องถิ่น"
    )
    pdf.bullet([
        "ข้อมูลหลัก: จุดความร้อนจากดาวเทียม, Sentinel-2 หรือ THEOS-2 สำหรับวิเคราะห์สภาพพืชพรรณ ความแห้งแล้ง และร่องรอยพื้นที่ไหม้, ข้อมูลฝนและสภาพอากาศ, ภูมิประเทศและความลาดชัน, land cover, ขอบเขตป่า, ขอบเขตป่าชุมชน และขอบเขตการปกครอง",
        "การสร้างตัวชี้วัด: ความหนาแน่นของจุดความร้อน ประวัติการเกิดไฟซ้ำ ความแห้งของพืชพรรณ ระยะใกล้ป่าและพื้นที่เกษตร ความลาดชัน ความผิดปกติของฝน และความใกล้ชุมชน",
        "AI/ML และ spatial analytics: จัดกลุ่มจุดความร้อน ให้คะแนนความเสี่ยง ตรวจจับพื้นที่ผิดปกติ และจัดลำดับพื้นที่ที่ควรดำเนินการก่อน",
        "Policy translation: แปลงผลวิเคราะห์เป็นชั้นข้อมูลแผนที่ รายงานสรุปรายสัปดาห์ พื้นที่เฝ้าระวัง และเหตุผลประกอบการตัดสินใจ"
    ])
    pdf.paragraph(
        "จุดเด่นคือระบบไม่ได้มองข้อมูลดาวเทียมเป็นเพียงภาพหรือจุดความร้อน แต่ตีความร่วมกับบริบทของพื้นที่ "
        "เช่น หากจุดความร้อนเกิดใกล้ป่าชุมชน อยู่ในพื้นที่ลาดชัน มีประวัติไฟซ้ำ และอยู่ใกล้ชุมชน "
        "ระบบจะจัดเป็นพื้นที่เฝ้าระวังลำดับสูงกว่าจุดความร้อนทั่วไป"
    )

    pdf.section("3. ผลลัพธ์ ความเป็นไปได้ และการนำไปใช้จริง")
    pdf.paragraph(
        "ผลลัพธ์ที่คาดหวังคือระบบต้นแบบ GeoAI Dashboard และ workflow สำหรับสนับสนุนการตัดสินใจด้านไฟป่าและหมอกควัน "
        "โดยเริ่มจากเชียงใหม่เป็นพื้นที่นำร่อง และออกแบบให้ขยายสู่จังหวัดอื่นในภาคเหนือได้"
    )
    pdf.bullet([
        "แผนที่ความเสี่ยงรายสัปดาห์และพื้นที่เฝ้าระวังลำดับสูง",
        "สรุปกลุ่มจุดความร้อนพร้อมเหตุผลว่าทำไมพื้นที่นั้นควรถูกจัดการก่อน",
        "ชั้นข้อมูลเชื่อมโยงพื้นที่เสี่ยงกับขอบเขตปกครองและหน่วยงานรับผิดชอบ",
        "ตัวชี้วัดความเสี่ยงของป่าชุมชนและพื้นที่ชายขอบป่า",
        "การจัดอันดับรายสัปดาห์ของพื้นที่หรือหน่วยงาน เพื่อใช้ติดตามผลการจัดการไฟและสนับสนุนการประชุม war room"
    ])
    pdf.paragraph(
        "โครงการมีความเป็นไปได้สูงเพราะสามารถใช้ข้อมูลเปิดและข้อมูลดาวเทียมที่มีอยู่ ร่วมกับต้นแบบ ChiangMaiEyes "
        "ซึ่งแสดงให้เห็นว่าทีมมีประสบการณ์ในการพัฒนา web-map dashboard และการออกแบบข้อมูลสำหรับบริบทไฟป่าและหมอกควันในเชียงใหม่แล้ว"
    )

    pdf.section("4. ศักยภาพทีมและการต่อยอดจาก ChiangMaiEyes")
    pdf.paragraph(
        "ทีมมีฐานการทำงานจาก ChiangMaiEyes ซึ่งเป็นต้นแบบแดชบอร์ดสำหรับติดตามไฟป่า หมอกควัน และข้อมูลพื้นที่ของเชียงใหม่ "
        "ข้อเสนอครั้งนี้จึงไม่เริ่มจากศูนย์ แต่ต่อยอดจากประสบการณ์เดิมให้เป็นกรอบ Fire-to-Policy GeoAI ที่กว้างขึ้นและมีมุม policy ชัดขึ้น"
    )
    pdf.bullet([
        "ทักษะที่ใช้: web-map development, geospatial data workflow, frontend/backend prototyping, data visualization, และการออกแบบข้อมูลเพื่อการตัดสินใจ",
        "บทบาทของ ChiangMaiEyes: เป็น pilot และหลักฐานว่าทีมเข้าใจปัญหาในพื้นที่จริง ไม่ใช่เพียงแนวคิดบนกระดาษ",
        "การขยายผล: จากเชียงใหม่สู่จังหวัดภาคเหนืออื่น โดยใช้ data model และ risk scoring framework เดียวกัน"
    ])
    pdf.callout(
        "สรุปความแตกต่างจาก ChiangMaiEyes เดิม",
        "ChiangMaiEyes เป็นฐานต้นแบบเชิงพื้นที่ ส่วน Fire-to-Policy GeoAI คือข้อเสนอใหม่ที่ยกระดับจาก dashboard ไปสู่ระบบจัดลำดับความเสี่ยง เชื่อมโยงความรับผิดชอบ และสร้างข้อมูลสนับสนุนนโยบายรายสัปดาห์"
    )

    pdf.section("5. ข้อความสำหรับลิงก์ Portfolio")
    pdf.paragraph(
        "ChiangMaiEyes prototype / demo / repository: [ใส่ลิงก์ของทีม]"
    )
    pdf.paragraph(
        "หมายเหตุ: ChiangMaiEyes ใช้เป็นต้นแบบนำร่องของข้อเสนอนี้ โดย GeoHackathon project จะขยายเป็น Fire-to-Policy GeoAI Framework "
        "ที่เน้น risk scoring, local authority responsibility, community forest intelligence, weekly policy summary และการขยายผลสู่ภาคเหนือ"
    )

    pdf.save()
    print(OUTPUT)


if __name__ == "__main__":
    build()
