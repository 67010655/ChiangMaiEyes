"""A single durable history read; no live upstream fan-out from analytics requests."""
from datetime import datetime,timezone,timedelta
from fastapi import HTTPException
from app.community_store import CommunityStore
from app.environment_archive import window,stamp,forest_index
from app.models import HistoryResponse,HotspotHistoryDay,DailyMetric,WeatherHistoryDay


def read_history(settings,days=30,*,end=None,as_of=None,forest_id=None,district=None):
    try:
        start,until=window(days,end)
        replay=stamp(as_of) if as_of else None
        if replay and replay>datetime.now(timezone.utc)+timedelta(minutes=5):
            raise ValueError('future replay')
    except (ValueError,TypeError,OverflowError):
        raise HTTPException(422,'เวลาต้องเป็น ISO พร้อมเขตเวลา และไม่ใช่อนาคต') from None
    if forest_id and forest_id not in {x[0] for x in forest_index()}:
        raise HTTPException(404,'ไม่พบขอบเขตป่าที่เลือก')
    r=CommunityStore(settings).call('POST','/rest/v1/rpc/cme_archive_analytics',json={
        'p_start':start.isoformat(),'p_end':until.isoformat(),'p_as_of':replay.isoformat() if replay else None,'p_forest':forest_id,**({'p_district':district.strip()} if district and district.strip() else {})})
    measured=[DailyMetric(date=x['date'],value=x['value']) for x in r['pm25'] if x['measurement_kind']=='measured']
    model=[DailyMetric(date=x['date'],value=x['value']) for x in r['pm25'] if x['measurement_kind']=='model']
    weather=[WeatherHistoryDay(**x) for x in r['weather'] if x['measurement_kind']=='model' and x['temp_max'] is not None and x['temp_min'] is not None]
    return HistoryResponse(days=days,start=r['start'],end=r['end'],as_of=r['as_of'],
        hotspots=[HotspotHistoryDay(**x) for x in r['hotspots']],pm25=measured,pm25_model=model,weather=weather,
        hour_histogram=r['hour_histogram'],analytics=r,latest_update=r['checked_at'],
        sources={'hotspots':'คลังจุดดาวเทียมที่ระบบได้รับ','pm25':'สถานีวัด แยกจากแบบจำลอง',
                 'pm25_model':'Open-Meteo CAMS global · จุดกริดอ้างอิงเมืองเชียงใหม่','weather':'Open-Meteo ERA5 / แบบจำลองที่เก็บไว้'},
        notes=['สถิติทุกกราฟใช้ช่วงเวลาเดียวกันตามเวลาไทย','นับการตรวจพบ ไม่ใช่จำนวนเหตุไฟที่ยืนยัน',
               'ชื่ออำเภอจากข้อมูลนำเข้าอาจเป็นการประมาณจากจุดอ้างอิง ต้องตรวจพิกัดก่อนใช้งาน',
               'ค่าเฉลี่ยฝุ่นเป็นค่าเฉลี่ยตัวอย่างที่ได้รับ ไม่ใช่ค่าเฉลี่ย 24 ชั่วโมงตามมาตรฐาน',
               'เว้นวันที่ข้อมูลไม่ครบจากการคำนวณค่าเฉลี่ยและความสัมพันธ์ ไม่เติมช่องว่างเป็นศูนย์'])
