from gurobipy import * 

import json 
from pprint import pprint
from itertools import combinations, zip_longest
from collections import defaultdict
from functools import lru_cache



def optimise_quests(quests_file, goals, bonuses, quest_overrides=None, all_items=False):
    if quest_overrides is None: quest_overrides = {}

    with open(quests_file) as f:
        quest_data = json.load(f)
    
    print('# FGO MIP')
    print('```')


    AP = {}
    Quests = {}
    Drops = {}
    Items = set()
    print('Initialising quest data...')
    for q in quest_data:
        assert q['title'] not in Quests
        Quests[q['title']] = q 
        AP[q['title']] = q['ap']
        Drops[q['title']] = drops = {}
        for drop in q['drops']:
            if drop['item'] not in drops:
                drops[drop['item']] = []
            drops[drop['item']].append(drop)
            Items.add(drop['item'])
    # pprint(Drops)
    
    GroupBonuses = {}
    GroupMax = {}
    Groups = tuple(bonuses.keys())
    for g, (limit, bonuses) in bonuses.items():
        GroupMax[g] = limit 
        GroupBonuses[g] = tuple(tuple(sorted(b.items())) for b in bonuses)

    def compute_single_bonus(bonus):
        total = {}
        for i, amt in bonus:
            if i not in total: total[i] = 0 
            total[i] += amt 
        return total

    @lru_cache(None)
    def compute_group_bonuses(bonus_list):
        total = {}
        for bonus in bonus_list:
            for i, amt in bonus:
                if i not in total: total[i] = 0 
                total[i] += amt 
        return total

    def compute_combs_set(g, drops):
        filtered_bonuses = [b for b in GroupBonuses[g] 
            if set(compute_single_bonus(b)) & drops]
        r = min(len(filtered_bonuses), GroupMax[g])
        return set(tuple(sorted(c))
                for c in combinations(filtered_bonuses, r))

    OptimalBonus = {}
    OptimalBonusAmounts = {}
    TotalQuestBonus = {}
    print('Computing optimal bonus configurations...')
    for q in Quests:
        if q in quest_overrides:
            OptimalBonus[q] = None 
            OptimalBonusAmounts[q] = {}
            TotalQuestBonus[q] = quest_overrides[q]
            continue

        dropped_items = {}
        for item, drops in Drops[q].items():
            if item not in dropped_items:
                dropped_items[item] = 0 
            for d in drops:
                dropped_items[d['item']] += d['percent']*d['num'] / 100
        priority = sorted(dropped_items.keys(), key=lambda k: dropped_items[k])
        priority = list(priority)
        # pprint(priority)

        OptimalBonus[q] = {}
        OptimalBonusAmounts[q] = {}
        # print(priority)
        for g in Groups:
            combs = list(compute_combs_set(g, set(priority)))
            for item in priority:
                combs.sort(key=lambda c: compute_group_bonuses(c).get(item, 0))
            OptimalBonus[q][g] = combs[-1]
            OptimalBonusAmounts[q][g] = compute_group_bonuses(combs[-1])
            # pprint(combs[-1])
        
        TotalQuestBonus[q] = {}
        for g, bonus in OptimalBonusAmounts[q].items():
            for i, amt in bonus.items():
                if i not in TotalQuestBonus[q]: TotalQuestBonus[q][i] = 0 
                TotalQuestBonus[q][i] += amt
    # pprint(BonusCombinations)
    # pprint(TotalBonus)
    # pprint(GIDs)

    m = Model('FGO')
    X = m.addVars(Quests, name='X', obj=AP, vtype=GRB.INTEGER)
    Z = m.addVars(Items, name='Z')

    print('Adding model constraints...')
    for i in Items:
        if not (i in goals or all_items): continue
        # print(i)
        m.addConstr(Z[i] == quicksum( 
            X[q] * sum(
                d['percent']/100*(
                    d['num'] + TotalQuestBonus[q].get(i, 0))
                for d in Drops[q].get(i, ()) )
            for q in X))

    m.addConstrs(Z[i] >= goals[i] for i in goals)

    m.setAttr(GRB.Attr.ModelSense, GRB.MINIMIZE)
    # m.setParam(GRB.Attr.MIPGap, 0.9/100)
    # m.write('model.lp')
    m.optimize()
    print('```')

    def format_bonus(bonus, sep=' '):
        s = []
        for mat, amt in bonus:
            s.append(mat.replace('/item/', '') + f'+{amt}')
        return sep.join(s)


    def format_groups(group_bonuses):
        out = []
        for bonus in group_bonuses:
            out.append(format_bonus(bonus))
        return ' | '.join(out)

    def print_quest_details(q):
        print('###', int(X[q].x), f'x {q} ({Quests[q]["location"]} {AP[q]} AP)')
        print('**Total bonus:**', TotalQuestBonus[q])
        print()
        if q in quest_overrides:
            print('Overriding bonuses for', q)
            return 
        print('', *Groups, '', sep=' | ')
        print('', *('---', )*len(Groups), '', sep=' | ')
        for bonus_row in zip_longest(*OptimalBonus[q].values()):
            print('', *(format_bonus(b) if b else '' for b in bonus_row),
                '', sep=' | ')

    print('## Quest Runs')
    optimal_quests = [(X[q].x, q) for q in X if X[q].x]
    optimal_quests.sort()
    for _, q in optimal_quests:
        print_quest_details(q)
        print()
    print('## Total AP:', '`', m.objVal, '`')
    print('## Total Drops')
    total_drops = [(Z[i].x, i) for i in Items if Z[i].x or i in goals]
    total_drops.sort(reverse=True)
    print(' | Amount | Item |')
    print(' | --- | --- |')
    for amt, item in total_drops:
        goals_str = f' / {goals[item]}' if item in goals else ''
        print('', f'{round(amt, 4)}{goals_str}',
            item, '', sep=' | ')
    print()

def main():
    water = '/item/fresh-water'
    food = '/item/food'
    wood = '/item/lumber'
    stone = '/item/stone'
    iron = '/item/iron'
    
    GOALS = {
        iron: 1500-1500,
        stone: 1500-1588,
        food: 2700-2700,
        water: 2700-2631,
        wood: 1800-1815,
    }

    SHOP_CE = {water: 2, food: 2}
    WOOD_CE = {wood: 1}
    STONE_CE = {stone: 1}
    IRON_CE = {iron: 1}

    SERVANTS = []
    for i in (water, food, wood, stone, iron):
        SERVANTS.extend(({i:1}, )*(5 if i != iron else 4))
    SERVANTS = tuple(SERVANTS)

    Bonuses = {
        'servants': (5, SERVANTS),
        'ces': (5, (SHOP_CE, WOOD_CE, WOOD_CE, {water: 1, food: 1})),
        'sup serv': (1, SERVANTS),
        'sup ce': (1, ({water: 2, food: 2}, {wood: 2}, {stone: 2}, {iron: 2})),
    }
    
    optimise_quests('summer1_quests.json', 
        GOALS, Bonuses, quest_overrides={
            'view-point-storm': {wood: 4, stone: 5, iron: 1},
            'romantic-cave-storm': {iron: 7, food: 2, water: 2},
        }, all_items=True)

if __name__ == "__main__":
    main()