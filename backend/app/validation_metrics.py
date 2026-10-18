"""Small deterministic metrics used by offline decision-support validation."""
import math


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def regression_metrics(pairs):
    rows=[r for r in pairs if finite(r['predicted']) and finite(r['observed'])]
    if not rows:
        return dict(n=0,mae=None,rmse=None,bias=None,correlation=None)
    errors=[r['predicted']-r['observed'] for r in rows]
    n=len(rows);pm=sum(r['predicted'] for r in rows)/n;om=sum(r['observed'] for r in rows)/n
    pp=sum((r['predicted']-pm)**2 for r in rows);oo=sum((r['observed']-om)**2 for r in rows)
    corr=sum((r['predicted']-pm)*(r['observed']-om) for r in rows)/math.sqrt(pp*oo) if pp*oo>0 else None
    return dict(n=n,mae=sum(abs(x) for x in errors)/n,rmse=math.sqrt(sum(x*x for x in errors)/n),
                bias=sum(errors)/n,correlation=corr)


def compare_models(rows, names):
    """Use identical valid references for every model; missing is never zero."""
    common=[r for r in rows if finite(r.get('observed')) and all(finite(r.get(k)) for k in names)]
    return common,{k:regression_metrics([{'observed':r['observed'],'predicted':r[k]} for r in common]) for k in names}


def skill_percent(model_mae, baseline_mae):
    if not finite(model_mae) or not finite(baseline_mae) or baseline_mae<=0:
        return None
    return 100*(1-model_mae/baseline_mae)
