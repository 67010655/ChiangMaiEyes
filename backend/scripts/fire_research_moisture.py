"""Scalar WRFx moisture equations used by the frozen offline benchmark.

Extracted unchanged from benchmark_open_fuels to avoid importing API routes.
Reference: https://github.com/openwfm/wrfxpy (MIT); source receipt is retained
under output/reference-tools/wrfxpy/SOURCE.json.
"""
import math

def equilibria(temperature,rh):
    """Van Wagner/Viney equations as implemented by WRF-SFIRE (mass fraction)."""
    h=float(rh);t=float(temperature)
    d=.942*h**.679+.00004994*math.exp(.1*h)+.18*(21.1-t)*(1-math.exp(-.115*h))
    w=.618*h**.753+.00004540*math.exp(.1*h)+.18*(21.1-t)*(1-math.exp(-.115*h))
    return max(d,w,0)/100,max(min(d,w),0)/100

def advance(state,d,w,rain):
    """Scalar counterpart of wrfxpy FuelMoistureModel.advance_model, dt=1h."""
    out=[]
    for m,lag in zip(state,(1,10,100)):
        if rain>.05:target=2.5;change=(1-math.exp(-(rain-.05)/8))/14
        else:target=d if m>d else w if m<w else m;change=1/lag
        factor=1-math.exp(-change) if change>.01 else change*(1-.5*change)
        out.append(m+(target-m)*factor)
    return tuple(out)
