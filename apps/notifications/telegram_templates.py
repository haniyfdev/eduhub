TEMPLATES = {
    "payment_reminder": {
        "uz": "📢 <b>To'lov eslatmasi</b>\n\nHurmatli <b>{full_name}</b>,\n\n<b>{course_name}</b> kursi uchun <b>{amount} so'm</b> to'lov muddati <b>{due_date}</b> gacha.\n\n🏫 {company_name}",
        "ru": "📢 <b>Напоминание об оплате</b>\n\nУважаемый(ая) <b>{full_name}</b>,\n\nОплата <b>{amount} сум</b> за курс <b>{course_name}</b> до <b>{due_date}</b>.\n\n🏫 {company_name}",
        "en": "📢 <b>Payment Reminder</b>\n\nDear <b>{full_name}</b>,\n\nPayment of <b>{amount} UZS</b> for <b>{course_name}</b> is due by <b>{due_date}</b>.\n\n🏫 {company_name}",
    },
    "payment_confirmed": {
        "uz": "✅ <b>To'lov tasdiqlandi</b>\n\nHurmatli <b>{full_name}</b>,\n\n<b>{amount} so'm</b> to'lovingiz muvaffaqiyatli qabul qilindi.\n\n🏫 {company_name}",
        "ru": "✅ <b>Оплата подтверждена</b>\n\nУважаемый(ая) <b>{full_name}</b>,\n\n<b>{amount} сум</b> успешно получено.\n\n🏫 {company_name}",
        "en": "✅ <b>Payment Confirmed</b>\n\nDear <b>{full_name}</b>,\n\n<b>{amount} UZS</b> has been successfully received.\n\n🏫 {company_name}",
    },
    "custom_message": {
        "uz": "📬 <b>{title}</b>\n\n{body}\n\n🏫 {company_name}",
        "ru": "📬 <b>{title}</b>\n\n{body}\n\n🏫 {company_name}",
        "en": "📬 <b>{title}</b>\n\n{body}\n\n🏫 {company_name}",
    },
    "group_announcement": {
        "uz": "📣 <b>{group_name} guruhi uchun xabar</b>\n\n{body}\n\n🏫 {company_name}",
        "ru": "📣 <b>Сообщение для группы {group_name}</b>\n\n{body}\n\n🏫 {company_name}",
        "en": "📣 <b>Message for {group_name} group</b>\n\n{body}\n\n🏫 {company_name}",
    },
}
