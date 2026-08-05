import numpy as np, pandas as pd
import build_deck as B
from grades import EYE
from score import score
from calibrated import score_cal
from variants import remeasure, HORIZON

rows=[]
for c in B.cards:
    i=c['i']; p=B.picks[i-1]; r=p['row']; d=p['frames'][c['sym']]; end=int(r['end'])
    sig=r.to_dict(); sig['detected']=True
    pm = r.get('prior_move') if p['market']=='US' else None
    ss = r.get('sector_share') if p['market']=='US' else None
    pm = None if (isinstance(pm,float) and np.isnan(pm)) else pm
    ss = None if (isinstance(ss,float) and np.isnan(ss)) else ss

    # decoupled: measure BOTH x2 dims over min(L_longest, 20), contraction as older-half vs recent-half
    m = remeasure(d, end, HORIZON)
    sigD = dict(sig); sigD['churn']=m['churn']; sigD['L_longest']=m['L_eff']
    sigD['contraction']=m['contraction_half']
    # keep the TRUE base length for the penalty dimension
    sigD['_true_L']=int(r['L_longest'])

    rows.append({'i':i,'sym':c['sym'],'eye':EYE[i],'trueL':int(r['L_longest']),
        'A_08':score(sig,pm,ss,'boolean')['stars'],
        'B_penalty':score_cal(sig,pm,ss,'boolean')['stars'],
        'C_decoupled':score(sigD,pm,ss,'boolean')['stars'],
        'D_both':score_cal({**sigD,'L_longest':int(r['L_longest']),
                            'churn':m['churn']*m['L_eff']/max(int(r['L_longest']),1)*0+m['churn'],
                            'contraction':m['contraction_half']},pm,ss,'boolean')['stars'],
        'D_cont':score_cal({**sigD,'L_longest':int(r['L_longest']),
                            'churn':m['churn'],'contraction':m['contraction_half']},pm,ss,'continuous')['stars'],
        })
df=pd.DataFrame(rows).sort_values('i'); pd.set_option('display.width',200)
print(df.round(2).to_string(index=False))
print(f"\nn={len(df)}; |r| must exceed ~0.38 for p<0.05")
print("NOTE: D_both scores orderliness on the 20-bar window but takes the length PENALTY from the true base length.\n")
for col in ['A_08','B_penalty','C_decoupled','D_both','D_cont']:
    e=df[col]-df.eye; r_=df[col].corr(df.eye)
    print(f"{col:12s} r={r_:+.3f} {'*' if abs(r_)>0.38 else ' '}  mean|err|={e.abs().mean():.2f}  within1={100*(e.abs()<=1).mean():.0f}%")
