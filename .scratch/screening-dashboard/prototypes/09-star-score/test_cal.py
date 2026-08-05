import numpy as np, pandas as pd
import build_deck as B
from grades import EYE
from score import score
from calibrated import score_cal
rows=[]
for c in B.cards:
    i=c['i']; p=B.picks[i-1]; r=p['row']; sig=r.to_dict(); sig['detected']=True
    pm = r.get('prior_move') if p['market']=='US' else None
    ss = r.get('sector_share') if p['market']=='US' else None
    pm = None if (isinstance(pm,float) and np.isnan(pm)) else pm
    ss = None if (isinstance(ss,float) and np.isnan(ss)) else ss
    rows.append({'i':i,'sym':c['sym'],'mkt':c['market'],'eye':EYE[i],
        'old':score(sig,pm,ss,'boolean')['stars'],
        'new':score_cal(sig,pm,ss,'boolean')['stars'],
        'new_cont':score_cal(sig,pm,ss,'continuous')['stars'],
        'L_longest':int(r['L_longest'])})
df=pd.DataFrame(rows).sort_values('i'); pd.set_option('display.width',200)
df['err_old']=df.old-df.eye; df['err_new']=df.new-df.eye
print(df[['i','sym','mkt','eye','old','new','new_cont','L_longest','err_old','err_new']].round(2).to_string(index=False))
print(f"\nn={len(df)}; |r| must exceed ~0.38 for p<0.05\n")
for col in ['old','new','new_cont']:
    e=df[col]-df.eye; r_=df[col].corr(df.eye)
    print(f"{col:9s} r={r_:+.3f} {'*' if abs(r_)>0.38 else ' '}  mean|err|={e.abs().mean():.2f}  within1={100*(e.abs()<=1).mean():.0f}%  meanerr={e.mean():+.2f}")
df.to_pickle('cache/cal_compare.pkl')
