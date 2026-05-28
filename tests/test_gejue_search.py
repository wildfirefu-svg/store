#!/usr/bin/env python3
"""P5 歌诀检索准确率测试 — 50+语义查询，相关度 ≥ 80%"""

import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'knowledge-base'))
from search_gejue import search

def run():
    # 50+ semantic queries with expected relevant song categories/tags
    queries = [
        # Category: 婚姻
        {"query":"什么时候结婚","expect_cat":"婚姻","expect_tags":["应期"],"note":"婚期查询"},
        {"query":"配偶是什么样的人","expect_cat":"婚姻","expect_tags":["配偶"],"note":"配偶特征"},
        {"query":"会不会离婚","expect_cat":"婚姻","expect_tags":["离婚"],"note":"离婚标志"},
        {"query":"晚婚还是早婚","expect_cat":"婚姻","expect_tags":["晚婚"],"note":"结婚时间"},
        {"query":"夫妻关系怎么样","expect_cat":"婚姻","expect_tags":["夫妻宫"],"note":"夫妻关系"},
        {"query":"二婚的命","expect_cat":"婚姻","expect_tags":["二婚"],"note":"再婚标志"},
        {"query":"配偶家有没有钱","expect_cat":"婚姻","expect_tags":["配偶"],"note":"配偶家境"},
        {"query":"女命婚姻","expect_cat":"婚姻","expect_tags":["女命"],"note":"女命婚姻"},
        {"query":"克夫吗","expect_cat":"婚姻","expect_tags":["伤官"],"note":"克夫判断"},

        # Category: 财运
        {"query":"怎么发财","expect_cat":"财运","expect_tags":["得财方式"],"note":"求财方式"},
        {"query":"什么时候有钱","expect_cat":"财运","expect_tags":["得财年"],"note":"得财时间"},
        {"query":"会不会破财","expect_cat":"财运","expect_tags":["破财"],"note":"破财预警"},
        {"query":"适合做投资吗","expect_cat":"财运","expect_tags":["投资"],"note":"投资建议"},
        {"query":"能存住钱吗","expect_cat":"财运","expect_tags":["财库"],"note":"守财能力"},
        {"query":"偏财运怎么样","expect_cat":"财运","expect_tags":["偏财"],"note":"偏财判断"},
        {"query":"正财运好不好","expect_cat":"财运","expect_tags":["正财"],"note":"正财判断"},
        {"query":"富屋贫人什么意思","expect_cat":"财运","expect_tags":["富屋贫人"],"note":"术语解释"},
        {"query":"合伙做生意能赚钱吗","expect_cat":"财运","expect_tags":["合作"],"note":"合伙财"},

        # Category: 官运/事业
        {"query":"什么时候能升职","expect_cat":"官运","expect_tags":["升迁"],"note":"升职时机"},
        {"query":"适合当官吗","expect_cat":"官运","expect_tags":["官星"],"note":"仕途判断"},
        {"query":"会不会有官灾","expect_cat":"官运","expect_tags":["官灾"],"note":"官灾预警"},
        {"query":"适合创业还是打工","expect_cat":"官运","expect_tags":["创业"],"note":"职业选择"},
        {"query":"公务员适合吗","expect_cat":"官运","expect_tags":["仕途"],"note":"职业建议"},
        {"query":"什么时候退休","expect_cat":"官运","expect_tags":["退休"],"note":"退休时机"},

        # Category: 疾病/健康
        {"query":"身体哪里容易出问题","expect_cat":"疾病","expect_tags":["五行"],"note":"健康五行"},
        {"query":"肝胆不好是什么原因","expect_cat":"疾病","expect_tags":["木"],"note":"肝胆五行"},
        {"query":"心脏要注意什么","expect_cat":"疾病","expect_tags":["火"],"note":"心脏五行"},
        {"query":"什么时候容易生病","expect_cat":"疾病","expect_tags":["发病年份"],"note":"发病时间"},
        {"query":"会不会有血光之灾","expect_cat":"疾病","expect_tags":["血光"],"note":"血光预警"},
        {"query":"失眠是什么命理原因","expect_cat":"疾病","expect_tags":["七杀"],"note":"失眠原因"},

        # Category: 流年
        {"query":"今年运势怎么样","expect_cat":"流年","expect_tags":["流年"],"note":"流年运势"},
        {"query":"本命年要注意什么","expect_cat":"流年","expect_tags":["值太岁"],"note":"本命年"},
        {"query":"犯太岁怎么办","expect_cat":"流年","expect_tags":["太岁"],"note":"太岁"},
        {"query":"明年能换工作吗","expect_cat":"流年","expect_tags":["变动"],"note":"工作变动"},
        {"query":"驿马年是什么意思","expect_cat":"流年","expect_tags":["驿马"],"note":"驿马"},
        {"query":"岁运并临会怎样","expect_cat":"流年","expect_tags":["岁运并临"],"note":"术语"},

        # Category: 小儿
        {"query":"小孩要注意什么健康问题","expect_cat":"小儿关煞","expect_tags":["儿童"],"note":"儿童健康"},
        {"query":"宝宝百日关是什么意思","expect_cat":"小儿关煞","expect_tags":["百日关"],"note":"百日关"},
        {"query":"孩子容易溺水吗","expect_cat":"小儿关煞","expect_tags":["落井关"],"note":"水厄"},

        # Category: 综合/技法
        {"query":"甲午日柱的人做什么职业","expect_cat":"综合","expect_tags":["带象"],"note":"带象职业"},
        {"query":"丁亥日柱好不好","expect_cat":"综合","expect_tags":["带象"],"note":"带象解读"},
        {"query":"铁口直断怎么用","expect_cat":"综合","expect_tags":["铁口直断"],"note":"技法"},
        {"query":"理象融合是什么","expect_cat":"综合","expect_tags":["理象融合"],"note":"心法"},
        {"query":"宾来生主好不好","expect_cat":"综合","expect_tags":["宾主"],"note":"宾主"},
        {"query":"看病找药怎么找","expect_cat":"综合","expect_tags":["病药"],"note":"病药说"},
        {"query":"做功是什么意思","expect_cat":"综合","expect_tags":["做功"],"note":"做功概念"},

        # Category: 万年桩/基础
        {"query":"怎么排八字","expect_cat":"万年桩","expect_tags":["排盘"],"note":"排盘方法"},
        {"query":"五虎遁是什么","expect_cat":"万年桩","expect_tags":["五虎遁"],"note":"基础口诀"},
        {"query":"节气怎么分月","expect_cat":"万年桩","expect_tags":["节气"],"note":"节气口诀"},
        {"query":"地支藏干怎么记","expect_cat":"万年桩","expect_tags":["藏干"],"note":"藏干口诀"},
    ]

    results = []
    categories_ok = 0
    tags_ok = 0
    total = len(queries)

    for i, q in enumerate(queries):
        top3 = search(q['query'], top_k=3)
        cats = [r['category'] for r in top3]
        all_tags = []
        for r in top3:
            all_tags.extend(r['tags'])

        # Check if expected category appears in TOP RESULT (most important)
        cat_match = (cats[0] if cats else '') == q['expect_cat']
        # Check if expected category appears in top 3 (relaxed)
        cat_top3 = q['expect_cat'] in cats
        # Check if ANY expected tag appears in top 3
        tag_match = any(t in all_tags for t in q['expect_tags'])

        if cat_match:
            categories_ok += 1
        if tag_match:
            tags_ok += 1

        results.append({
            'query': q['query'],
            'expect_cat': q['expect_cat'],
            'got_cats': cats,
            'expect_tags': q['expect_tags'],
            'got_tags_match': tag_match,
            'cat_match': cat_match,
            'note': q['note'],
        })

    cat_acc = categories_ok / total * 100
    tag_acc = tags_ok / total * 100
    # Practical accuracy: top-1 category match OR tag match in top-3
    practical = sum(1 for r in results if r['cat_match'] or r['got_tags_match']) / total * 100

    print(f'=== 歌诀检索准确率测试 ===')
    print(f'总查询: {total}')
    print(f'Top-1类别命中: {categories_ok}/{total} = {cat_acc:.1f}%')
    print(f'Top-3标签命中: {tags_ok}/{total} = {tag_acc:.1f}%')
    print(f'实用准确率 (类别OR标签): {practical:.1f}%')
    print()

    # Show misses (neither cat nor tag matched)
    misses = [r for r in results if not r['cat_match'] and not r['got_tags_match']]
    if misses:
        print(f'=== 未命中 ({len(misses)}) ===')
        for m in misses:
            print(f'  "{m["query"]}": expected={m["expect_cat"]}, got={m["got_cats"][:2]}')
    print()

    if practical >= 80:
        print(f'PASS: 实用准确率 {practical:.1f}% >= 80%')
    else:
        print(f'BELOW: 实用准确率 {practical:.1f}% < 80%')

    out = os.path.join(os.path.dirname(__file__), 'gejue_search_report.json')
    json.dump({
        'total': total, 'cat_accuracy': round(cat_acc,1),
        'tag_accuracy': round(tag_acc,1), 'practical': round(practical,1),
        'results': results
    }, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Report: {out}')

if __name__ == '__main__':
    run()
