from datetime import datetime

def execute_exit(symbol, data, exit_price, final_pct, reason):
    global CURRENT_BALANCE
    
    # 1. حساب وقت الخروج والمدة المستغرقة
    exit_time_dt = datetime.now()
    exit_time_str = exit_time_dt.strftime("%Y-%m-%d %H:%M")
    
    # تحويل وقت الدخول النصي إلى كائن datetime للحساب
    entry_time_dt = datetime.strptime(data['entry_time'], "%Y-%m-%d %H:%M")
    duration = exit_time_dt - entry_time_dt
    
    # تنسيق المدة (ساعات ودقائق)
    hours, remainder = divmod(duration.total_seconds(), 3600)
    minutes, _ = divmod(remainder, 60)
    duration_str = f"{int(hours)}س {int(minutes)}د" if hours > 0 else f"{int(minutes)}د"

    # 2. حساب الأرباح بالدولار
    profit_usd = data['invested_amount'] * (final_pct / 100)
    
    # 3. تسجيل الصفقة في السجل اليومي مع إضافة "المدة"
    trade_log = {
        "symbol": symbol, 
        "entry_p": data['entry_price'], 
        "exit_p": round(exit_price, 5),
        "amount": round(data['invested_amount'], 2), 
        "pct": round(final_pct, 2),
        "usd": round(profit_usd, 2), 
        "in_time": data['entry_time'], 
        "out_time": exit_time_str,
        "duration": duration_str # إضافة مدة الصفقة للسجل
    }
    db["daily_trades"].append(trade_log)
    
    # 4. تحديث الرصيد وحفظ البيانات
    CURRENT_BALANCE += (data['invested_amount'] + profit_usd)
    db["balance"] = CURRENT_BALANCE
    save_db(db)

    # 5. إشعار التليجرام المحدث
    icon = "💎" if final_pct > 0 else "🛑"
    status = "✅ ربح" if final_pct > 0 else "❌ خسارة"
    
    send_telegram(f"{icon} **إغلاق صفقة: {symbol}**\n━━━━━━━━━━━━━━\n"
                  f"📊 النتيجة: `{final_pct:+.2f}%` ({status})\n"
                  f"💵 الربح/الخسارة: `${profit_usd:+.2f}`\n"
                  f"⏱️ مدة الصفقة: `{duration_str}`\n"
                  f"📥 دخول: `{data['entry_price']}`\n"
                  f"📤 خروج: `{exit_price:.5f}`\n"
                  f"🏦 الرصيد الجديد: `${CURRENT_BALANCE:.2f}`")

# التعديل المطلوب في التقرير اليومي لعرض المدة أيضاً:
def send_daily_summary():
    if not db["daily_trades"]:
        send_telegram("📅 **تقرير اليوم:** لا صفقات مغلقة.")
        return
    
    msg = "📅 **ملخص الصفقات اليومي (المدة والنتائج)**\n━━━━━━━━━━━━━━\n"
    for t in db["daily_trades"]:
        msg += f"🪙 `{t['symbol']}` | `{t['pct']}%` | `{t['duration']}`\n"
    
    msg += f"━━━━━━━━━━━━━━\n🏦 الرصيد النهائي: `${CURRENT_BALANCE:.2f}`"
    send_telegram(msg)
    db["daily_trades"] = []
    save_db(db)
