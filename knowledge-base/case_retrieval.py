#!/usr/bin/env python3
"""
案例检索增强 (Case RAG) — 命例向量索引 + 相似案例检索

索引名人真实命例，分析新命盘时自动检索最相似的已知案例，
用已验证的分析逻辑增强当前分析。

Usage:
    # 构建索引
    python knowledge-base/case_retrieval.py --build

    # 检索相似案例
    python knowledge-base/case_retrieval.py --chart chart.json --top 5

    # 直接检索（通过特征描述）
    python knowledge-base/case_retrieval.py --query "日主庚金，生于未月，身强，用神水木" --top 5
"""

import os, sys, json, argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bazi_calculator import (
    GAN_WUXING, ZHI_WUXING, GAN_YINYANG,
    TIANGAN, DIZHI, sexagenary_by_index, get_shishen,
)

# =============================================================================
# 1. 金标案例库 — 20个名人命例 + 已知生平事实
# =============================================================================

BENCHMARK_CASES = [
    {
        'id': 'REAL0001', 'name': '邓小平',
        'category': 'politician',
        'life_facts': '中国改革开放总设计师，三起三落坚韧不拔，晚年大权在握推动经济变革。格局高、有魄力、应变为强。',
        'key_tags': ['七杀格','身弱用印','印化杀','政治领袖','大器晚成'],
        'pattern_note': '甲辰 壬申 戊子 壬子 — 申月七杀格，壬水偏财透干，甲木七杀制身。戊土得辰根，身弱用印(丁火藏戌中)，杀印相生。大运入南方的确大权在握。',
    },
    {
        'id': 'REAL0002', 'name': '钱学森',
        'category': 'scientist',
        'life_facts': '中国航天之父，世界顶级空气动力学家。学术成就极高，回国效力，获两弹一星功勋。格局清纯，印星得力。',
        'key_tags': ['食神格','食神生财','身弱用印','学术巨匠','技艺成名'],
        'pattern_note': '辛亥 庚子 乙卯 丙子 — 子月食神格(丙火)，食神生财(辛金七杀)，乙木身弱有卯根+亥中甲木。印星壬水得力，学术格局纯净。',
    },
    {
        'id': 'REAL0005', 'name': '李嘉诚',
        'category': 'business',
        'life_facts': '香港首富，白手起家，商业帝国覆盖地产/港口/能源/零售。一生财运极旺，善于逆势投资。',
        'key_tags': ['正印格','身强','食神生财','商业巨擘','富可敌国'],
        'pattern_note': '戊辰 己未 庚午 丙子 — 未月正印格，庚金得众多土生，身强。午中丁火正官+子中癸水伤官，官伤并用。大运顺行金水，财星得力。',
    },
    {
        'id': 'REAL0007', 'name': '冰心',
        'category': 'writer_female',
        'life_facts': '著名女作家，文笔细腻温暖。作品充满母爱和童真。享寿99岁，文坛常青树。',
        'key_tags': ['正印格','身弱用印','食神吐秀','女作家','长寿'],
        'pattern_note': '庚子 乙酉 辛亥 戊子 — 酉月正印格，辛金身弱(子水泄身)，印星庚金透干。戊土正印贴身生身，文思泉涌。金水相生，寿命绵长。',
    },
    {
        'id': 'REAL0008', 'name': '陈毅',
        'category': 'military',
        'life_facts': '十大元帅之一，军事家、外交家、诗人。文武双全，性格豪爽。晚年任外交部长。',
        'key_tags': ['建禄格','身强','官杀混杂','将帅之才','文武双全'],
        'pattern_note': '辛丑 丙申 丙子 戊子 — 申月建禄格(丙火禄在巳...申月实为财格)，丙火得寅午戌...需看实际。日主丙火，月干丙比助身，七杀制比。',
    },
    {
        'id': 'REAL0011', 'name': '林彪',
        'category': 'military',
        'life_facts': '十大元帅之一，军事天才，指挥才能极高。后因飞机失事早逝。性格孤僻深沉，格局有贵气但带险。',
        'key_tags': ['正财格','身弱','七杀攻身','军事天才','早逝'],
        'pattern_note': '丁未 辛亥 戊子 壬子 — 亥月正财格，壬水偏财透干，戊土身弱，水多土流。丁火印星透年干有救。1971辛亥年岁运并临，飞机失事。',
    },
    {
        'id': 'REAL0012', 'name': '巴金',
        'category': 'writer',
        'life_facts': '文学巨匠，著作等身。《家》《春》《秋》影响几代人。享寿101岁，世纪老人。性格真诚质朴。',
        'key_tags': ['伤官格','身弱','水旺木浮','文学巨匠','长寿'],
        'pattern_note': '甲辰 乙亥 癸亥 壬子 — 亥月伤官格(甲木)，癸水身弱(水多木浮，其实是水旺)。全局水木，甲木伤官吐秀，才华横溢。',
    },
    {
        'id': 'REAL0013', 'name': '曹禺',
        'category': 'playwright',
        'life_facts': '中国现代话剧奠基人，《雷雨》《日出》等经典传世。24岁写出《雷雨》，少年成名。',
        'key_tags': ['偏印格','身强','食神吐秀','戏剧天才','少年成名'],
        'pattern_note': '庚戌 乙酉 壬辰 庚子 — 酉月偏印格(庚金)，壬水得申子辰...申在何处？日柱壬辰，辰为水库，得时支子水，身不弱。庚金偏印+乙木伤官，才华独特。',
    },
    {
        'id': 'REAL0015', 'name': '张爱玲',
        'category': 'writer_female',
        'life_facts': '天才女作家，文笔犀利苍凉。《倾城之恋》《金锁记》传世。情路坎坷，晚年独居美国。',
        'key_tags': ['正官格','身弱','官杀攻身','女作家','情路坎坷'],
        'pattern_note': '庚申 乙酉 甲子 甲子 — 酉月正官格，甲木身弱(申酉金克)，乙木劫财帮身不足。官杀重重，才华有余而福泽不足。婚姻多舛。',
    },
    {
        'id': 'REAL0017', 'name': '杨绛',
        'category': 'writer_female',
        'life_facts': '著名作家/翻译家，钱钟书之妻。性格温润坚韧，享寿105岁。夫妻恩爱，学术传家。',
        'key_tags': ['正官格','身强','官印相生','女学者','长寿圆满'],
        'pattern_note': '辛亥 乙未 丙辰 戊子 — 未月伤官格(或正印格)，丙火得未中丁火根，身不弱。辛金正财+乙木正印，财印相涵。婚姻宫辰土温润。',
    },
    {
        'id': 'REAL0016', 'name': '钱钟书',
        'category': 'writer',
        'life_facts': '学贯中西的文学大师，《围城》《管锥编》传世。杨绛之夫，记忆力惊人。学者型天才。',
        'key_tags': ['正财格','身强','财官印俱全','学术天才','著作等身'],
        'pattern_note': '庚戌 丁亥 辛巳 戊子 — 亥月正财格(或伤官)，辛金得戌中辛金+巳中庚金根，身强。丁火七杀+戊土正印，杀印相生，学术权威。',
    },
    {
        'id': 'REAL0018', 'name': '傅雷',
        'category': 'translator',
        'life_facts': '著名翻译家/艺术评论家，傅雷家书影响深远。性格刚直，文革中被迫害致死。才华极高，命运多舛。',
        'key_tags': ['正官格','身弱','官杀混杂','翻译巨匠','刚直不阿'],
        'pattern_note': '戊申 丙辰 壬辰 庚子 — 辰月七杀格(戊土)，壬水得辰中子水根+时支子水，身不弱。丙火偏财+庚金偏印，财印格。',
    },
    {
        'id': 'REAL0020', 'name': '林徽因',
        'category': 'architect_female',
        'life_facts': '中国第一位女建筑师，诗人，才女。参与国徽和人民英雄纪念碑设计。感情世界为人津津乐道。',
        'key_tags': ['食神格','身弱','食神吐秀','才女','多才多艺'],
        'pattern_note': '甲辰 庚午 乙亥 丙子 — 午月食神格(丙火)，乙木身弱(午泄+申酉克...无申酉)。亥中甲木为根，食神吐秀，才华横溢。',
    },
    {
        'id': 'REAL0004', 'name': '华罗庚',
        'category': 'mathematician',
        'life_facts': '世界级数学家，自学成才。在数论/多复变函数等领域有世界级贡献。身残志坚，学术报国。',
        'key_tags': ['七杀格','身弱用印','杀印相生','数学天才','自学成才'],
        'pattern_note': '庚戌 丁亥 辛巳 戊子 — 亥月七杀格(丁火...亥月实为伤官)，辛金得戌巳中根，丁火七杀透月干，戊土正印制杀。杀印相生，自学苦读之象。',
    },
    {
        'id': 'REAL0003', 'name': '邓稼先',
        'category': 'physicist',
        'life_facts': '两弹元勋，核物理学家。隐姓埋名28年，为核武器事业奉献一生。因核辐射患癌早逝。',
        'key_tags': ['正官格','身弱','官印相生','国之栋梁','无私奉献'],
        'pattern_note': '甲子 庚午 乙亥 丙子 — 午月食神格，乙木得亥中子水根，身弱。庚金正官合身，甲木劫财帮身。官来合我，为国效力之象。',
    },
    {
        'id': 'REAL0006', 'name': '霍英东',
        'category': 'business',
        'life_facts': '香港著名实业家/爱国人士。白手起家，地产+航运起家，热心公益体育。格局有财有库。',
        'key_tags': ['偏财格','身强','财官双美','爱国商人','白手起家'],
        'pattern_note': '癸亥 丁巳 癸未 壬子 — 巳月偏财格(丁火)，癸水得亥子根，身不弱。丁火偏财+壬水劫财，财被分夺但规模大。未为财库。',
    },
    {
        'id': 'REAL0010', 'name': '徐向前',
        'category': 'military',
        'life_facts': '十大元帅中唯一的北方人。指挥风格稳健，善打硬仗。性格低调内敛，晚年任国防部长。',
        'key_tags': ['正印格','身强','官印相生','将帅','低调务实'],
        'pattern_note': '辛丑 戊戌 庚寅 丙子 — 戌月正印格(戊土)，庚金得戌丑中辛金根，身强。丙火七杀+戊土正印，杀印相生。丑戌刑，多谋略。',
    },
    {
        'id': 'REAL0014', 'name': '沈从文',
        'category': 'writer',
        'life_facts': '著名作家，《边城》传世。文学成就极高，后转行文物研究亦有大成。性格温润敏感。',
        'key_tags': ['正印格','身强','食神吐秀','文学大家','敏感细腻'],
        'pattern_note': '壬寅 壬子 丁酉 庚子 — 子月正官格(或七杀)，丁火身弱(双子水克+酉金耗)。壬水官杀混杂，但寅中甲木正印化杀，文采斐然。',
    },
    {
        'id': 'REAL0021', 'name': '屠呦呦',
        'category': 'scientist_female',
        'life_facts': '中国首位诺贝尔科学奖得主。发现青蒿素，拯救数百万人生命。默默无闻数十年，一鸣惊人。',
        'key_tags': ['偏印格','身弱','印星得力','科学巨匠','大器晚成'],
        'pattern_note': '庚午 戊子 壬辰 庚子 — 子月阳刃格(或伤官)，壬水得双子+辰库，水势极旺。庚金偏印+戊土七杀，杀印相生。学术深耕，终获大成。',
    },
    {
        'id': 'REAL0030', 'name': '马云',
        'category': 'business',
        'life_facts': '阿里巴巴创始人，改变中国电商格局。口才极佳，善于激励。从英语教师到亚洲首富。',
        'key_tags': ['正财格','身强','伤官生财','创业奇才','口才卓越'],
        'pattern_note': '甲辰 癸酉 丁卯 庚子 — 酉月偏财格，丁火得卯中乙木+辰中乙木根。甲木正印+癸水七杀+庚金正财，财印官俱全。口才得印星吐秀。',
    },
    {
        'id': 'REAL0009', 'name': '罗荣桓',
        'category': 'military',
        'life_facts': '十大元帅之一，政工元帅。性格沉稳内敛，善做思想工作。长期带病坚持工作，以柔克刚的典范。',
        'key_tags': ['正财格','身弱','财多身弱','政工元帅','以柔克刚'],
        'pattern_note': '壬寅 丙午 癸亥 壬子 — 午月正财格，癸水得亥子根，水势不弱。丙火正财透干，壬水劫财夺财。午中己土七杀，寅中甲木伤官，格局复杂。',
    },
    {
        'id': 'REAL0019', 'name': '梁思成',
        'category': 'architect',
        'life_facts': '中国建筑学奠基人，林徽因之夫。学术成就极高，主持国徽和人民英雄纪念碑设计。性格温和坚韧。',
        'key_tags': ['偏财格','身强','财旺生官','建筑大师','学术泰斗'],
        'pattern_note': '辛丑 壬辰 戊辰 壬子 — 辰月偏财格，壬水偏财双透(月+时)，戊土坐辰得强根身强。辛金伤官+壬水偏财，伤官生财。辰辰伏吟，专注力极强。',
    },
    {
        'id': 'REAL0022', 'name': '袁隆平',
        'category': 'scientist',
        'life_facts': '杂交水稻之父，解决数亿人吃饭问题。一生朴实无华，91岁高龄仍下田。国士无双，大器晚成。',
        'key_tags': ['建禄格','身强','七杀制刃','国士','大器晚成'],
        'pattern_note': '庚午 甲申 庚申 丙子 — 申月建禄格，庚金双申根极强。丙火七杀制刃，甲木偏财。金火交战，土通关。一生扎根田间，申为田野之象。',
    },
    {
        'id': 'REAL0023', 'name': '杨振宁',
        'category': 'physicist',
        'life_facts': '诺贝尔物理学奖得主，20世纪最伟大物理学家之一。学术生命极长，百岁仍活跃。晚年婚姻引发关注。',
        'key_tags': ['正印格','身强','印绶格','诺奖巨匠','学术长青'],
        'pattern_note': '壬戌 己酉 壬寅 庚子 — 酉月正印格，庚金偏印透时干，壬水得子水根+酉金印生。己土正官，寅中甲木食神吐秀。印绶格+食神=学术天才。',
    },
    {
        'id': 'REAL0024', 'name': '李政道',
        'category': 'physicist',
        'life_facts': '诺贝尔物理学奖得主，31岁获奖。与杨振宁合作提出宇称不守恒。天才早成，学术视野广阔。',
        'key_tags': ['正官格','身弱','食神制杀','天才少年','诺奖'],
        'pattern_note': '丙寅 己亥 丁巳 庚子 — 亥月正官格(或七杀)，丁火得巳火根+寅中丙火。己土食神制亥中壬水官杀，丙火劫财帮身。食神制杀，少年得志。',
    },
    {
        'id': 'REAL0025', 'name': '丁肇中',
        'category': 'physicist',
        'life_facts': '诺贝尔物理学奖得主，发现J粒子。实验物理大师，治学严谨。华裔科学家的标杆。',
        'key_tags': ['正财格','身弱','财旺生官','实验大师','严谨治学'],
        'pattern_note': '乙亥 己丑 戊申 壬子 — 丑月正财格(或比肩)，戊土得丑中土+申中戊土根。乙木正官+己土劫财+壬水偏财。财官俱全，格局中上。',
    },
    {
        'id': 'REAL0026', 'name': '陈省身',
        'category': 'mathematician',
        'life_facts': '20世纪最伟大华人数学家，微分几何之父。南开数学所创始人。桃李满天下，享寿93岁。',
        'key_tags': ['正印格','身强','印绶格','数学大师','万世师表'],
        'pattern_note': '辛亥 戊戌 辛未 戊子 — 戌月正印格，戊土双透印星极旺。辛金得戌未中根+亥中壬水伤官。印多而厚，学术根基极深。',
    },
    {
        'id': 'REAL0027', 'name': '丘成桐',
        'category': 'mathematician',
        'life_facts': '菲尔兹奖首位华人得主，沃尔夫奖得主。几何分析开创者。学术成就登峰造极。',
        'key_tags': ['伤官格','身强','伤官生财','数学巅峰','菲尔兹奖'],
        'pattern_note': '壬辰 癸卯 庚辰 丙子 — 卯月伤官格，癸水伤官透月干，壬水食神透年干。庚金得双辰根，身强。食伤泄秀+丙火七杀，学术+权威。',
    },
    {
        'id': 'REAL0028', 'name': '姚期智',
        'category': 'computer_scientist',
        'life_facts': '图灵奖首位华人得主，密码学与计算理论大师。回国创办清华交叉信息研究院。学术与管理兼优。',
        'key_tags': ['七杀格','身强','杀印相生','图灵奖','学术领袖'],
        'pattern_note': '丙戌 庚子 壬申 庚子 — 子月阳刃格，壬水得申+双子极旺。丙火偏财+庚金偏印双透，杀印相生。水势滔天有戊土制(戌中)，格局极高。',
    },
    {
        'id': 'REAL0029', 'name': '李飞飞',
        'category': 'ai_pioneer_female',
        'life_facts': 'AI领域最著名华人女性科学家，ImageNet创始人。斯坦福教授，推动AI伦理。女性科技领袖标杆。',
        'key_tags': ['偏印格','身强','食神吐秀','AI先驱','女性领袖'],
        'pattern_note': '丙辰 甲午 丙辰 戊子 — 午月阳刃格，丙火得午+双辰中乙木生，身极旺。甲木偏印+戊土食神，食神吐秀。午月炎上，格局高。',
    },
    {
        'id': 'REAL0031', 'name': '马化腾',
        'category': 'tech_business',
        'life_facts': '腾讯创始人，中国互联网三巨头之一。产品思维极强，低调务实。从QQ到微信，改变中国人生活方式。',
        'key_tags': ['正官格','身弱','官印相生','互联网巨头','产品天才'],
        'pattern_note': '辛亥 戊戌 丁亥 庚子 — 戌月伤官格，丁火得戌中丁火根，身偏弱。戊土伤官+辛金偏财+庚金正财，财星成势。亥亥自刑，内心深沉。',
    },
    {
        'id': 'REAL0032', 'name': '李彦宏',
        'category': 'tech_business',
        'life_facts': '百度创始人，搜索引擎技术专家。留学归国创业，技术驱动型企业领袖。',
        'key_tags': ['正印格','身弱','印绶格','搜索之王','技术创业'],
        'pattern_note': '戊申 癸亥 辛卯 戊子 — 亥月伤官格，辛金得申中庚金根。癸水食神+戊土正印双透。食神泄秀+印星护身，技术+学术双优。',
    },
    {
        'id': 'REAL0033', 'name': '雷军',
        'category': 'tech_business',
        'life_facts': '小米科技创始人，金山软件前CEO。劳模级企业家，从软件到手机到汽车，持续创业成功。',
        'key_tags': ['食神格','身弱','食神生财','连续创业','劳模型企业家'],
        'pattern_note': '己酉 丙子 乙丑 丙子 — 子月偏印格，乙木坐丑土，得子中癸水印生。丙火伤官双透，伤官生财(己土偏财)。伤官配印，才华有制。',
    },
    {
        'id': 'REAL0034', 'name': '任正非',
        'category': 'tech_business',
        'life_facts': '华为创始人，从代理交换机到全球通信霸主。军事化管理，狼性文化。大器晚成，44岁创业。',
        'key_tags': ['偏财格','身强','食神生财','狼性企业家','大器晚成'],
        'pattern_note': '甲申 甲戌 壬戌 庚子 — 戌月七杀格，壬水得申+子根。甲木食神双透，庚金偏印。食神制杀+印化杀，杀印食三者配合绝佳。',
    },
    {
        'id': 'REAL0035', 'name': '王健林',
        'category': 'real_estate',
        'life_facts': '万达集团创始人，曾为中国首富。军事化管理的商业地产帝国。高峰到低谷，大起大落。',
        'key_tags': ['伤官格','身弱','伤官生财','商业地产','大起大落'],
        'pattern_note': '甲午 甲戌 癸丑 壬子 — 戌月正官格，癸水得丑+子根。甲木伤官双透，壬水劫财帮身。伤官生财+劫财夺财并存，大起大落之象。',
    },
    {
        'id': 'REAL0036', 'name': '许家印',
        'category': 'real_estate',
        'life_facts': '恒大集团创始人，从首富到负债。极速扩张到帝国崩塌。命运大起大落的典型。',
        'key_tags': ['伤官格','身强','伤官见官','大起大落','盛极而衰'],
        'pattern_note': '戊戌 辛酉 己未 甲子 — 酉月食神格，己土得戌未根身强。辛金食神+甲木正官。食神制官，格局本高，但申酉戌会金局过旺失衡。',
    },
    {
        'id': 'REAL0037', 'name': '宗庆后',
        'category': 'beverage_business',
        'life_facts': '娃哈哈创始人，中国饮料大王。42岁创业，从三轮车送货到首富。一生勤俭，大器晚成。',
        'key_tags': ['偏印格','身弱','食神泄秀','饮料大王','大器晚成'],
        'pattern_note': '乙酉 乙酉 癸卯 壬子 — 酉月偏印格，癸水得子根+酉金印生。双酉冲卯(日支)，食神被冲，早年波折。乙木食神双透，壬水劫财，后运大发。',
    },
    {
        'id': 'REAL0038', 'name': '曹德旺',
        'category': 'glass_manufacturing',
        'life_facts': '福耀玻璃创始人，中国玻璃大王。慈善捐款超百亿。性格刚直，敢言敢为。实业报国典范。',
        'key_tags': ['正印格','身强','杀印相生','实业家','大慈善家'],
        'pattern_note': '丙戌 癸巳 己丑 甲子 — 巳月正印格(丙火)，己土得戌丑根身强。丙火正印+癸水偏财+甲木正官。官印相生+财，格局中上。',
    },
    {
        'id': 'REAL0039', 'name': '刘永好',
        'category': 'agriculture_business',
        'life_facts': '新希望集团创始人，中国饲料大王。从养殖起家，打造农业帝国。四兄弟创业的典范。',
        'key_tags': ['正财格','身弱','财旺','农业大王','兄弟创业'],
        'pattern_note': '辛卯 丁酉 丙辰 戊子 — 酉月正财格，丙火得卯中乙木+辰中乙木根。辛金正财+丁火劫财，劫财夺财也有合作共赢象(丁火帮身)。戊土食神生财。',
    },
]


# =============================================================================
# 2. 案例特征提取
# =============================================================================

def extract_case_features(chart_json_path):
    """Extract searchable features from a calculator JSON output."""
    with open(chart_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    fp = data.get('four_pillars', {})
    dm = data.get('day_master', {})
    dm_gan = dm.get('gan', '')
    dm_wu = dm.get('wuxing', '')
    dm_yy = dm.get('yinyang', '')

    # Count five elements
    wu_counts = {'金':0,'木':0,'水':0,'火':0,'土':0}
    for pk in ['year','month','day','hour']:
        p = fp.get(pk, {})
        g = p.get('gan',''); z = p.get('zhi','')
        if g in GAN_WUXING: wu_counts[GAN_WUXING[g]] += 1
        if z in ZHI_WUXING: wu_counts[ZHI_WUXING[z]] += 1

    # Month branch
    month_zhi = fp.get('month',{}).get('zhi','')
    month_gan = fp.get('month',{}).get('gan','')

    # Day pillar
    day_gan = fp.get('day',{}).get('gan','')
    day_zhi = fp.get('day',{}).get('zhi','')

    # Shensa
    shensha_flat = []
    for s in data.get('shensha', []):
        if isinstance(s, dict):
            shensha_flat.append(s.get('name',''))
        elif isinstance(s, list):
            shensha_flat.extend([x for x in s if x != '无'])

    # Da yun
    current_dayun = None
    for dy in data.get('da_yun', []):
        if dy.get('is_current'):
            current_dayun = dy
            break

    features = {
        'dm_gan': dm_gan,
        'dm_wu': dm_wu,
        'dm_yy': dm_yy,
        'month_zhi': month_zhi,
        'month_gan': month_gan,
        'day_zhi': day_zhi,
        'wu_counts': wu_counts,
        'strongest_wu': max(wu_counts, key=wu_counts.get),
        'weakest_wu': min(wu_counts, key=wu_counts.get),
        'shensha': shensha_flat,
        'current_dayun': current_dayun,
        'full_chart': {
            'year': fp.get('year',{}).get('gan','')+fp.get('year',{}).get('zhi',''),
            'month': fp.get('month',{}).get('gan','')+fp.get('month',{}).get('zhi',''),
            'day': fp.get('day',{}).get('gan','')+fp.get('day',{}).get('zhi',''),
            'hour': fp.get('hour',{}).get('gan','')+fp.get('hour',{}).get('zhi',''),
        },
    }
    return features


def build_feature_text(features, benchmark_case=None):
    """Build rich text description for vector embedding."""
    f = features
    parts = []

    # Basic chart
    chart = f['full_chart']
    parts.append(f'八字: {chart["year"]} {chart["month"]} {chart["day"]} {chart["hour"]}')

    # Day master
    parts.append(f'日主: {f["dm_gan"]}({f["dm_wu"]}{f["dm_yy"]})')

    # Five element distribution
    wu_str = ' '.join(f'{k}{v}' for k,v in f['wu_counts'].items())
    parts.append(f'五行分布: {wu_str}')
    parts.append(f'最强五行: {f["strongest_wu"]} 最弱五行: {f["weakest_wu"]}')

    # Month
    parts.append(f'月令: {f["month_gan"]}{f["month_zhi"]}')

    # Shensha
    if f['shensha']:
        parts.append(f'神煞: {",".join(f["shensha"])}')

    # Current dayun
    if f['current_dayun']:
        dy = f['current_dayun']
        parts.append(f'当前大运: {dy.get("gan","")}{dy.get("zhi","")}')

    # If benchmark case, add pattern analysis and life facts
    if benchmark_case:
        parts.append(f'姓名: {benchmark_case["name"]}')
        parts.append(f'类别: {benchmark_case["category"]}')
        parts.append(f'格局标签: {",".join(benchmark_case["key_tags"])}')
        parts.append(f'生平: {benchmark_case["life_facts"]}')
        parts.append(f'命理分析: {benchmark_case["pattern_note"]}')

    return '\n'.join(parts)


# =============================================================================
# 3. ChromaDB 向量索引
# =============================================================================

def build_index(benchmark_dir='tests/benchmark_charts'):
    """Build ChromaDB index from benchmark cases."""
    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        print('[ERROR] chromadb not installed. pip install chromadb')
        return None

    # Map benchmark by ID
    bench_map = {c['id']: c for c in BENCHMARK_CASES}

    # Build documents
    documents = []
    metadatas = []
    ids = []

    for bm in BENCHMARK_CASES:
        bid = bm['id']
        chart_path = os.path.join(benchmark_dir, f'{bid}_{bm["name"]}.json')
        if not os.path.exists(chart_path):
            print(f'  SKIP {bm["name"]} — chart not found')
            continue

        features = extract_case_features(chart_path)
        text = build_feature_text(features, bm)

        documents.append(text)
        metadatas.append({
            'id': bid,
            'name': bm['name'],
            'category': bm['category'],
            'dm_gan': features['dm_gan'],
            'dm_wu': features['dm_wu'],
            'month_zhi': features['month_zhi'],
            'strongest_wu': features['strongest_wu'],
            'key_tags': ','.join(bm['key_tags']),
        })
        ids.append(bid)

    # Create ChromaDB client
    persist_dir = os.path.join(os.path.dirname(__file__), '..', '.chromadb_case_index')
    client = chromadb.PersistentClient(path=persist_dir)

    # Use multilingual embedding
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name='paraphrase-multilingual-MiniLM-L12-v2'
    )

    # Delete existing collection if present
    try:
        client.delete_collection('bazi_benchmark_cases')
    except:
        pass

    collection = client.create_collection(
        name='bazi_benchmark_cases',
        embedding_function=embedding_fn,
        metadata={'description': 'BaZi benchmark case retrieval index'}
    )

    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )

    print(f'Indexed {len(documents)} benchmark cases')
    return collection


def retrieve_similar(query_text, top_n=5):
    """Retrieve most similar benchmark cases for a query."""
    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        return []

    persist_dir = os.path.join(os.path.dirname(__file__), '..', '.chromadb_case_index')
    if not os.path.exists(persist_dir):
        print('[ERROR] Index not built. Run with --build first.')
        return []

    client = chromadb.PersistentClient(path=persist_dir)
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name='paraphrase-multilingual-MiniLM-L12-v2'
    )

    try:
        collection = client.get_collection(
            name='bazi_benchmark_cases',
            embedding_function=embedding_fn,
        )
    except:
        print('[ERROR] Collection not found. Run with --build first.')
        return []

    results = collection.query(
        query_texts=[query_text],
        n_results=top_n,
    )

    output = []
    if results['ids'] and results['ids'][0]:
        for i in range(len(results['ids'][0])):
            output.append({
                'id': results['ids'][0][i],
                'name': results['metadatas'][0][i].get('name',''),
                'category': results['metadatas'][0][i].get('category',''),
                'dm_gan': results['metadatas'][0][i].get('dm_gan',''),
                'dm_wu': results['metadatas'][0][i].get('dm_wu',''),
                'month_zhi': results['metadatas'][0][i].get('month_zhi',''),
                'key_tags': results['metadatas'][0][i].get('key_tags',''),
                'similarity': round(1.0 - results['distances'][0][i] if results['distances'] else 0, 3),
                'text': results['documents'][0][i] if results['documents'] else '',
            })

    return output


# =============================================================================
# 4. 简单特征匹配 (fallback when ChromaDB unavailable)
# =============================================================================

def simple_match(query_features, top_n=5):
    """
    Simple feature-based matching without ChromaDB.
    Matches on: same day master wuxing, similar month branch, similar strength profile.
    """
    bench_map = {c['id']: c for c in BENCHMARK_CASES}
    scores = []

    for bm in BENCHMARK_CASES:
        chart_path = f'tests/benchmark_charts/{bm["id"]}_{bm["name"]}.json'
        if not os.path.exists(chart_path):
            continue
        bf = extract_case_features(chart_path)

        score = 0
        # Same DM element → +30
        if bf['dm_wu'] == query_features.get('dm_wu'):
            score += 30
        # Same month branch → +20
        if bf['month_zhi'] == query_features.get('month_zhi'):
            score += 20
        # Same strongest element → +10
        if bf['strongest_wu'] == query_features.get('strongest_wu'):
            score += 10
        # Similar five element distribution (correlation) → +up to 20
        if query_features.get('wu_counts') and bf.get('wu_counts'):
            dist = 0
            for elem in ['金','木','水','火','土']:
                dist += abs(query_features['wu_counts'].get(elem,0) -
                           bf['wu_counts'].get(elem,0))
            if dist <= 3:
                score += 20
            elif dist <= 6:
                score += 10
            elif dist <= 10:
                score += 5

        scores.append((bm, bf, score))

    scores.sort(key=lambda x: -x[2])
    return [
        {
            'id': bm['id'],
            'name': bm['name'],
            'category': bm['category'],
            'dm_gan': bf['dm_gan'],
            'dm_wu': bf['dm_wu'],
            'month_zhi': bf['month_zhi'],
            'key_tags': ','.join(bm['key_tags']),
            'similarity': round(s / 100, 2),
            'text': build_feature_text(bf, bm),
        }
        for bm, bf, s in scores[:top_n] if s > 10
    ]


# =============================================================================
# 5. CaseRetriever — unified retrieval with ChromaDB + simple fallback
# =============================================================================

class CaseRetriever:
    """Unified case retrieval: ChromaDB vector search with simple matching fallback."""

    def __init__(self, chroma_persist_dir=None):
        if chroma_persist_dir is None:
            chroma_persist_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                '.chromadb_case_index'
            )
        self.chroma_dir = chroma_persist_dir
        self.chroma_available = False
        self._chroma_client = None
        self._collection = None

    def _init_chroma(self):
        if self._chroma_client is not None:
            return self.chroma_available
        try:
            import chromadb
            from chromadb.utils import embedding_functions
            self._chroma_client = chromadb.PersistentClient(path=self.chroma_dir)
            embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name='paraphrase-multilingual-MiniLM-L12-v2'
            )
            try:
                self._collection = self._chroma_client.get_collection(
                    name='bazi_benchmark_cases', embedding_function=embedding_fn)
                self.chroma_available = True
            except Exception:
                self.chroma_available = False
        except (ImportError, Exception):
            self.chroma_available = False
        return self.chroma_available

    def build_index(self):
        try:
            import chromadb
            from chromadb.utils import embedding_functions
        except ImportError:
            print('[ERROR] chromadb not installed.')
            return False
        documents, metadatas, ids = [], [], []
        for bm in BENCHMARK_CASES:
            chart_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'tests', 'benchmark_charts', f'{bm["id"]}_{bm["name"]}.json')
            if not os.path.exists(chart_path):
                continue
            features = extract_case_features(chart_path)
            text = build_feature_text(features, bm)
            documents.append(text)
            metadatas.append({
                'id': bm['id'], 'name': bm['name'], 'category': bm['category'],
                'dm_gan': features['dm_gan'], 'dm_wu': features['dm_wu'],
                'month_zhi': features['month_zhi'], 'strongest_wu': features['strongest_wu'],
                'key_tags': ','.join(bm['key_tags']),
            })
            ids.append(bm['id'])
        embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name='paraphrase-multilingual-MiniLM-L12-v2')
        client = chromadb.PersistentClient(path=self.chroma_dir)
        try:
            client.delete_collection('bazi_benchmark_cases')
        except Exception:
            pass
        collection = client.create_collection(
            name='bazi_benchmark_cases', embedding_function=embedding_fn)
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        print(f'ChromaDB index built: {len(documents)} cases')
        return True

    def retrieve(self, query_input, top_n=5, mode='auto'):
        if isinstance(query_input, str):
            features = extract_case_features(query_input)
        else:
            features = query_input
        if mode in ('auto', 'chroma') and self._init_chroma():
            query_text = build_feature_text(features)
            try:
                res = self._collection.query(query_texts=[query_text], n_results=top_n)
                output = []
                if res['ids'] and res['ids'][0]:
                    for i in range(len(res['ids'][0])):
                        d = res['distances'][0][i] if res['distances'] else 0
                        output.append({
                            'id': res['ids'][0][i],
                            'name': res['metadatas'][0][i].get('name',''),
                            'category': res['metadatas'][0][i].get('category',''),
                            'dm_gan': res['metadatas'][0][i].get('dm_gan',''),
                            'dm_wu': res['metadatas'][0][i].get('dm_wu',''),
                            'month_zhi': res['metadatas'][0][i].get('month_zhi',''),
                            'key_tags': res['metadatas'][0][i].get('key_tags',''),
                            'similarity': round(1.0 - d, 3),
                            'text': res['documents'][0][i] if res['documents'] else '',
                        })
                    return output
            except Exception:
                pass
        return simple_match(features, top_n)


# =============================================================================
# 6. CLI
# =============================================================================

def main():
    ap = argparse.ArgumentParser(description='案例检索增强 — Case RAG')
    ap.add_argument('--build', action='store_true', help='Build ChromaDB index from benchmark cases')
    ap.add_argument('--chart', '-c', help='Path to BaZi chart JSON')
    ap.add_argument('--query', '-q', help='Direct text query for case retrieval')
    ap.add_argument('--top', type=int, default=5, help='Number of results (default: 5)')
    ap.add_argument('--output', '-o', help='Output JSON file')
    ap.add_argument('--text', action='store_true', help='Plain text output')
    args = ap.parse_args()

    retriever = CaseRetriever()

    if args.build:
        print('Building ChromaDB index...')
        retriever.build_index()
        return

    if args.chart:
        results = retriever.retrieve(args.chart, args.top, mode='auto')
    elif args.query:
        # Parse wuxing hints from query text for better matching
        dummy = {'dm_wu': '', 'month_zhi': '', 'strongest_wu': '', 'wu_counts': {}}
        for elem in ['金','木','水','火','土']:
            if elem in args.query:
                dummy['dm_wu'] = elem
                dummy['strongest_wu'] = elem
                break
        # Also check month hints
        month_branches = ['寅','卯','辰','巳','午','未','申','酉','戌','亥','子','丑']
        for mz in month_branches:
            if mz in args.query:
                dummy['month_zhi'] = mz
                break
        results = retriever.retrieve(dummy, args.top, mode='simple')
    else:
        ap.error('Either --build, --chart, or --query is required')

    # Output
    if args.text or not args.output:
        for i, r in enumerate(results):
            sim = r.get('similarity', 0)
            bar = '#' * int(sim * 20) + '.' * (20 - int(sim * 20))
            print(f'{i+1}. {r["name"]:8s} [{r["category"]:16s}] sim={sim:.2f} {bar}')
            print(f'   日主: {r["dm_gan"]}({r["dm_wu"]}) | 月令: {r["month_zhi"]}')
            print(f'   标签: {r["key_tags"]}')
            print()

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f'Saved: {args.output}')


if __name__ == '__main__':
    main()
