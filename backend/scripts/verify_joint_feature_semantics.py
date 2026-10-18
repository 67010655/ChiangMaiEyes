"""Small causal/time and meteorological convention checks, isolated research env."""
from datetime import datetime,timedelta,timezone
import numpy as np
from joint_fire_experiment import pm_features,wind_features,COLS,GROUPS,ICT,BASE_NAMES,WIND_NAMES,PM_NAMES

origin=datetime(2026,3,10,8,tzinfo=ICT)
data={'pm':{'2026-03-08':{'35T':20,'36T':40},'2026-03-07':{'35T':10,'36T':30},
             '2026-03-09':{'35T':9999,'36T':9999},'2026-03-10':{'35T':8888,'36T':8888}}}
first=pm_features(data,origin)
assert first[2]==np.float32(np.log1p(30))
data['pm']['2026-03-09']={'35T':0,'36T':0};data['pm']['2026-03-10']={'35T':0,'36T':0}
np.testing.assert_array_equal(first,pm_features(data,origin))

t=origin.timestamp();hourly={'wind_speed_10m_previous_day1':[3.]*12,'wind_direction_10m_previous_day1':[270.]*12}
winddata={'met_index':{t+i*3600:i for i in range(12)},'met':[{'hourly':hourly}],
  'wind_centres':np.array([[0.,0.]]),'wind_grid_index':np.array([0,0]),
  'times':np.array([t-4*3600]),'xy':np.array([[0.,0.]])}
grid={'xy':np.array([[1000.,0.],[-1000.,0.]])}
eastwest=wind_features(winddata,origin,grid)
assert eastwest.shape==(2,16)
np.testing.assert_allclose(eastwest[:,0],3,atol=1e-6)
np.testing.assert_allclose(eastwest[:,1],0,atol=1e-6)
np.testing.assert_allclose(eastwest[:,11],[1,-1],atol=1e-6)
assert eastwest[0,14]>eastwest[0,15] and eastwest[1,14]<eastwest[1,15]

# A detection only1h before issue is not usable under the3h source delay.
winddata['times']=np.r_[winddata['times'],t-3600];winddata['xy']=np.vstack([winddata['xy'],[999.,0.]])
np.testing.assert_array_equal(eastwest,wind_features(winddata,origin,grid))
assert len(BASE_NAMES)==27 and len(WIND_NAMES)==16 and len(PM_NAMES)==10
assert set(COLS[GROUPS[0]])<set(COLS[GROUPS[1]])<set(COLS[GROUPS[3]])
assert not set(COLS[GROUPS[2]])&set(range(27,43))
assert max(COLS[GROUPS[3]])==52
print('PASS: PM uses only earlier dates; wind-from converts to downwind correctly; hotspot3h delay excludes future inputs; feature groups separate cleanly.')
