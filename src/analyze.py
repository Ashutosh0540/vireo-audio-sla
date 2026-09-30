from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/"data"; OUT=ROOT/"output"; OUT.mkdir(exist_ok=True)
SLA={"chat":15,"voice":120,"social":240,"email":480}

def shift(dt):
    h=dt.hour+dt.minute/60
    return "Morning" if 6<=h<14 else ("Day" if 14<=h<22 else "Night")

t=pd.read_csv(DATA/"tickets.csv")
a=pd.read_csv(DATA/"agents.csv")
for c in ["created_at","first_response_at","resolved_at"]:
    t[c]=pd.to_datetime(t[c],utc=True,errors="coerce")
t["_helpdesk"]=t["source_system"].eq("helpdesk").astype(int)
t=t.sort_values(["ticket_id","_helpdesk"],ascending=[True,False]).drop_duplicates("ticket_id").copy()
t["created_ist"]=t.created_at.dt.tz_convert("Asia/Kolkata")
t["response_minutes"]=(t.first_response_at-t.created_at).dt.total_seconds()/60
t["sla_minutes"]=t.channel.map(SLA)
t["breach"]=t.first_response_at.notna() & (t.response_minutes>t.sla_minutes)
# Retain Tuesday-Monday weeks (W-MON means week ENDING Monday).
# Drop timezone only after conversion to IST, avoiding the to_period warning.
# Clip edge-week labels to observed coverage; do not alter ticket timestamps.
created_dates=t.created_ist.dt.tz_localize(None).dt.normalize()
weeks=created_dates.dt.to_period("W-MON")
week_start=weeks.dt.start_time.clip(lower=created_dates.min())
week_end=weeks.dt.end_time.dt.normalize().clip(upper=created_dates.max())
t["week"]=week_start.dt.strftime("%Y-%m-%d")+"/"+week_end.dt.strftime("%Y-%m-%d")
t["created_shift"]=t.created_ist.apply(shift)
t["overnight_created"]=t.created_shift.eq("Night")
t["sla_credit_inr"]=t.breach.astype(int)*350

a["from_date"]=pd.to_datetime(a.from_date,errors="coerce").fillna(pd.Timestamp("1900-01-01"))
a["to_date"]=pd.to_datetime(a.to_date,errors="coerce").fillna(pd.Timestamp("2100-01-01"))
event=t.resolved_at.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None).dt.normalize()
event=event.fillna(t.created_ist.dt.tz_localize(None).dt.normalize())
t["_event_date"]=event
m=t.merge(a[["agent_id","name","site","team","shift","tier","from_date","to_date"]],on="agent_id",how="left")
ok=(m._event_date>=m.from_date)&(m._event_date<=m.to_date)
m=m[ok].copy()
m["_span"]=(m.to_date-m.from_date).dt.days
t=m.sort_values(["ticket_id","_span"]).drop_duplicates("ticket_id").copy()

def agg(g):
    x=g.groupby(g.name if hasattr(g,"name") else None)

overall=pd.DataFrame([{
    "tickets":len(t),"breaches":int(t.breach.sum()),"breach_rate":t.breach.mean(),
    "sla_credits_inr":int(t.sla_credit_inr.sum()),
    "overnight_tickets":int(t.overnight_created.sum()),
    "overnight_breach_rate":t.loc[t.overnight_created,"breach"].mean()
}])
weekly=t.groupby("week",as_index=False).agg(tickets=("ticket_id","count"),breaches=("breach","sum"),credits_inr=("sla_credit_inr","sum"))
weekly["breach_rate"]=weekly.breaches/weekly.tickets
# Additional client deliverable: reuse the existing creation week and matched
# resolving-agent roster shift. Include all tiers for complete reconciliation;
# this is a reporting breakdown, not a cross-tier performance ranking.
weekly_agent_shift=t.groupby(["week","agent_id","name","shift"],dropna=False,as_index=False).agg(
    ticket_count=("ticket_id","count"),
    breach_count=("breach","sum"),
    breach_rate=("breach","mean"),
    sla_credits=("sla_credit_inr","sum"),
).rename(columns={"name":"agent_name"})
weekly_agent_shift.to_csv(OUT/"weekly_agent_shift_breaches.csv",index=False)
shift_df=t.groupby("shift",as_index=False).agg(tickets=("ticket_id","count"),breaches=("breach","sum"),credits_inr=("sla_credit_inr","sum"))
shift_df["breach_rate"]=shift_df.breaches/shift_df.tickets
channel=t.groupby("channel",as_index=False).agg(tickets=("ticket_id","count"),breaches=("breach","sum"),credits_inr=("sla_credit_inr","sum"))
channel["breach_rate"]=channel.breaches/channel.tickets
tier1=t[~t["tier"].astype(str).str.contains("2",na=False)].copy()
agent=tier1.groupby(["agent_id","name","site","team","shift","tier"],dropna=False,as_index=False).agg(tickets=("ticket_id","count"),breaches=("breach","sum"),credits_inr=("sla_credit_inr","sum"))
agent["breach_rate"]=agent.breaches/agent.tickets
overnight=t.groupby("overnight_created",as_index=False).agg(tickets=("ticket_id","count"),breaches=("breach","sum"),credits_inr=("sla_credit_inr","sum"))
overnight["breach_rate"]=overnight.breaches/overnight.tickets

for name,df in {"overall":overall,"weekly_summary":weekly,"shift_summary":shift_df,"channel_summary":channel,"agent_summary_tier1":agent,"overnight_summary":overnight,"ticket_audit":t}.items():
    df.to_csv(OUT/f"{name}.csv",index=False)

print(overall.to_string(index=False))
print("\nSHIFT\n",shift_df.to_string(index=False))
print(f"\nWeekly agent/shift report: {len(weekly_agent_shift)} rows -> {OUT/'weekly_agent_shift_breaches.csv'}")

# Planning only: use elapsed IST calendar coverage, not the count of reporting
# bins (the first/last bins are partial). This does not alter any ticket facts.
coverage_days=(t.created_ist.max().normalize()-t.created_ist.min().normalize()).days+1
coverage_weeks=coverage_days/7
weekly_volume=len(t)/coverage_weeks
scenario_rate=0.15
fewer_breaches_per_week=(t.breach.mean()-scenario_rate)*weekly_volume
quarterly_avoided_credits=fewer_breaches_per_week*350*13
print("\nPLANNING SCENARIO (not a Vireo target; conditional, not guaranteed savings)")
print(f"Observed coverage: {coverage_days} days / 7 = {coverage_weeks:g} week equivalents")
print(f"Observed tickets/week: {weekly_volume:.6f}")
print(f"Proposed breach rate: {scenario_rate:.2%}")
print(f"Fewer breaches/week at unchanged volume: {fewer_breaches_per_week:.6f}")
print(f"Avoided SLA credits over 13 weeks (INR): {quarterly_avoided_credits:.2f}")
