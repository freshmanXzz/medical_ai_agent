"""Render a stable PNG case report for the README."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "docs" / "case_report_demo.png"
FONT_REGULAR = Path("C:/Windows/Fonts/msyh.ttc")
FONT_BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")

WIDTH = 1600
HEIGHT = 2200
MARGIN = 86
CONTENT_LEFT = 122
CONTENT_RIGHT = WIDTH - 122

COLORS = {
    "background": "#edf2f4",
    "paper": "#ffffff",
    "navy": "#19384c",
    "ink": "#1d2933",
    "muted": "#66737e",
    "line": "#d7e0e5",
    "green": "#26745f",
    "green_soft": "#e7f2ee",
    "amber": "#aa6519",
    "amber_soft": "#fff3df",
    "red": "#a33a3a",
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(str(path), size=size)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, text_font, max_width: int):
    lines = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for character in paragraph:
            candidate = current + character
            if draw.textlength(candidate, font=text_font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = character
        if current:
            lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    text_font,
    fill: str,
    max_width: int,
    line_height: int,
) -> int:
    x, y = xy
    for line in wrap_text(draw, text, text_font, max_width):
        draw.text((x, y), line, font=text_font, fill=fill)
        y += line_height
    return y


def section_title(draw: ImageDraw.ImageDraw, y: int, number: str, title: str) -> int:
    draw.text((CONTENT_LEFT, y), number, font=font(22, True), fill=COLORS["green"])
    draw.text((CONTENT_LEFT + 52, y - 4), title, font=font(32, True), fill=COLORS["navy"])
    draw.line(
        (CONTENT_LEFT, y + 48, CONTENT_RIGHT, y + 48),
        fill=COLORS["line"],
        width=2,
    )
    return y + 70


def key_value(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    value: str,
    width: int,
) -> None:
    draw.text((x, y), label, font=font(21, True), fill=COLORS["muted"])
    draw_wrapped(
        draw,
        value,
        (x + 145, y - 2),
        font(22),
        COLORS["ink"],
        width - 145,
        34,
    )


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["background"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (MARGIN, 54, WIDTH - MARGIN, HEIGHT - 54),
        radius=8,
        fill=COLORS["paper"],
        outline=COLORS["line"],
        width=2,
    )

    draw.rectangle((MARGIN, 54, WIDTH - MARGIN, 294), fill=COLORS["navy"])
    draw.text(
        (CONTENT_LEFT, 92),
        "MARTIN MEDICAL AI",
        font=font(22, True),
        fill="#8ed0bc",
    )
    draw.text(
        (CONTENT_LEFT, 134),
        "肺部 CT 智能辅助病例报告",
        font=font(48, True),
        fill="#ffffff",
    )
    draw.text(
        (CONTENT_LEFT, 215),
        "报告编号  MARTIN-DEMO-20260714-001",
        font=font(20),
        fill="#c6d4dc",
    )
    draw.text(
        (1050, 215),
        "检查日期  2026-07-14",
        font=font(20),
        fill="#c6d4dc",
    )

    draw.rounded_rectangle(
        (CONTENT_LEFT, 330, CONTENT_RIGHT, 432),
        radius=6,
        fill=COLORS["green_soft"],
    )
    draw.text(
        (CONTENT_LEFT + 24, 352),
        "示例数据说明",
        font=font(22, True),
        fill=COLORS["green"],
    )
    draw.text(
        (CONTENT_LEFT + 210, 352),
        "患者资料为模拟；结节数量、尺寸、坐标和置信度来自项目实际检测输出。",
        font=font(22),
        fill=COLORS["ink"],
    )
    draw.text(
        (CONTENT_LEFT + 210, 388),
        "本图仅用于项目演示，不代表真实患者诊断。",
        font=font(21),
        fill=COLORS["muted"],
    )

    y = section_title(draw, 480, "01", "患者资料（模拟）")
    column_width = (CONTENT_RIGHT - CONTENT_LEFT - 40) // 2
    key_value(draw, CONTENT_LEFT, y, "年龄/性别", "62 岁 / 男", column_width)
    key_value(draw, CONTENT_LEFT + column_width + 40, y, "主诉", "咳嗽 2 周", column_width)
    y += 62
    key_value(draw, CONTENT_LEFT, y, "吸烟史", "30 包年", column_width)
    key_value(draw, CONTENT_LEFT + column_width + 40, y, "家族史", "肺癌家族史阴性", column_width)
    y += 62
    key_value(draw, CONTENT_LEFT, y, "伴随症状", "无咯血、胸痛及明显气促", column_width)
    key_value(draw, CONTENT_LEFT + column_width + 40, y, "既往影像", "未提供", column_width)

    y = section_title(draw, y + 94, "02", "检查与模型信息")
    key_value(draw, CONTENT_LEFT, y, "检查文件", "1.3.6.1.4.1.14519...005112.nii.gz", CONTENT_RIGHT - CONTENT_LEFT)
    y += 62
    key_value(draw, CONTENT_LEFT, y, "检测模型", "MONAI 3D RetinaNet", column_width)
    key_value(draw, CONTENT_LEFT + column_width + 40, y, "检出数量", "1 个候选肺结节", column_width)

    y = section_title(draw, y + 96, "03", "AI 影像检测结果")
    table_top = y
    row_height = 60
    columns = [CONTENT_LEFT, 220, 430, 690, 960, CONTENT_RIGHT]
    headers = ["编号", "最大径", "三维尺寸", "置信度", "世界坐标"]
    draw.rectangle(
        (CONTENT_LEFT, table_top, CONTENT_RIGHT, table_top + row_height),
        fill="#f2f6f8",
    )
    for index, header in enumerate(headers):
        draw.text(
            (columns[index] + 12, table_top + 15),
            header,
            font=font(20, True),
            fill=COLORS["muted"],
        )
    values = ["1", "4.94 mm", "4.89 × 4.94 × 4.94 mm", "99.47%", "(-64.00, -5.09, -85.45) mm"]
    for index, value in enumerate(values):
        draw.text(
            (columns[index] + 12, table_top + row_height + 18),
            value,
            font=font(20),
            fill=COLORS["ink"],
        )
    draw.line(
        (CONTENT_LEFT, table_top + row_height * 2, CONTENT_RIGHT, table_top + row_height * 2),
        fill=COLORS["line"],
        width=2,
    )
    y = table_top + row_height * 2 + 28
    draw.text((CONTENT_LEFT, y), "定位与形态", font=font(21, True), fill=COLORS["muted"])
    y = draw_wrapped(
        draw,
        "检测输出仅提供世界坐标，未提供肺叶/肺段、实性或亚实性密度、边缘、钙化及胸膜关系；以上信息需由放射科医生复核原始薄层 CT。",
        (CONTENT_LEFT + 170, y - 2),
        font(21),
        COLORS["ink"],
        CONTENT_RIGHT - CONTENT_LEFT - 170,
        34,
    )

    y = section_title(draw, y + 42, "04", "辅助印象")
    impression = (
        "1. AI 模型检出单发小结节候选灶，最大径约 4.94 mm，检测置信度 99.47%。\n"
        "2. 当前数据不足以判断结节密度、形态及生长情况，不能据此确诊良恶性。\n"
        "3. 当前资料无法完成可靠的 Lung-RADS 分级。"
    )
    y = draw_wrapped(
        draw,
        impression,
        (CONTENT_LEFT, y),
        font(23),
        COLORS["ink"],
        CONTENT_RIGHT - CONTENT_LEFT,
        42,
    )

    y = section_title(draw, y + 34, "05", "风险信息与建议")
    draw.rounded_rectangle(
        (CONTENT_LEFT, y, CONTENT_RIGHT, y + 92),
        radius=6,
        fill=COLORS["amber_soft"],
    )
    draw.text(
        (CONTENT_LEFT + 20, y + 18),
        "风险背景",
        font=font(22, True),
        fill=COLORS["amber"],
    )
    draw_wrapped(
        draw,
        "模拟患者年龄及长期吸烟史会提高肺癌基线风险；咳嗽本身缺乏特异性，不能由该结节直接解释。",
        (CONTENT_LEFT + 155, y + 16),
        font(21),
        COLORS["ink"],
        CONTENT_RIGHT - CONTENT_LEFT - 175,
        34,
    )
    y += 122
    recommendations = (
        "1. 由放射科医生复核原始薄层 CT，补充肺叶定位、结节密度、边缘、钙化和其他胸部异常。\n"
        "2. 如有既往 CT，应进行同层面对比，确认结节是否新发及有无增长。\n"
        "3. 由呼吸科或放射科结合完整影像特征、筛查场景和个人风险决定随访方案。\n"
        "4. 若出现咯血、明显呼吸困难、持续胸痛等症状，应及时线下就医。"
    )
    y = draw_wrapped(
        draw,
        recommendations,
        (CONTENT_LEFT, y),
        font(22),
        COLORS["ink"],
        CONTENT_RIGHT - CONTENT_LEFT,
        39,
    )

    y = section_title(draw, y + 28, "06", "数据局限与声明")
    limitations = (
        "本报告基于自动检测结果生成。模型置信度不等同于恶性概率；未进行完整胸部 CT 征象判读，也不能替代放射科报告、病理检查或临床诊断。"
    )
    y = draw_wrapped(
        draw,
        limitations,
        (CONTENT_LEFT, y),
        font(21),
        COLORS["muted"],
        CONTENT_RIGHT - CONTENT_LEFT,
        36,
    )
    draw.text(
        (CONTENT_LEFT, HEIGHT - 108),
        "AI ASSISTED · PHYSICIAN REVIEW REQUIRED",
        font=font(18, True),
        fill=COLORS["red"],
    )
    draw.text(
        (1110, HEIGHT - 108),
        "Martin v0.1.0",
        font=font(18),
        fill=COLORS["muted"],
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT_PATH, format="PNG", optimize=True)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
