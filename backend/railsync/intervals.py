from datetime import timedelta
import math

def intersect(a,b):
    start=max(a[0],b[0]);end=min(a[1],b[1]);return (start,end) if start<end else None

def merge(intervals):
    result=[]
    for start,end in sorted(intervals):
        if result and start<=result[-1][1]:result[-1]=(result[-1][0],max(end,result[-1][1]))
        else:result.append((start,end))
    return result

def subtract(allowed,blocked):
    result=[]
    for start,end in allowed:
        cursor=start
        for bstart,bend in merge(blocked):
            if bend<=cursor or bstart>=end:continue
            if cursor<bstart:result.append((cursor,min(bstart,end)))
            cursor=max(cursor,bend)
            if cursor>=end:break
        if cursor<end:result.append((cursor,end))
    return result

def common_windows(per_track):
    result=per_track[0]
    for windows in per_track[1:]:result=[x for a in result for b in windows if (x:=intersect(a,b))]
    return merge(result)

def minute(value,horizon_start,mode):
    raw=(value-horizon_start).total_seconds()/60
    return math.floor(raw) if mode=='floor' else math.ceil(raw)
