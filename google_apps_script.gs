/**
 * Google Apps Script — заказы: строка в таблицу + бронь в календаре Bakery_Dasha.
 * Плюс doGet(?count=DD.MM.YYYY) — возвращает число подтверждённых заказов на дату
 * (n8n использует это для лимита «N тортов в день»).
 *
 * Колонки: Date | Time | Event Date | People | Tiers | Decor | Delivery |
 *          Total Amount | Deposit | Client | Status
 *
 * НАСТРОЙКА:
 *  1. Таблица → Расширения → Apps Script → вставь ВЕСЬ файл → Сохрани.
 *  2. Deploy → Manage deployments → ✏️ → New version → Deploy
 *     (или New deployment → Web app: Execute as Me, Access Anyone).
 *  3. Google попросит разрешения (Таблицы + Календарь) — нажми Authorize.
 *  4. Скопируй /exec URL → проверь в браузере ("ok") → вставь в n8n LOG_URL.
 */

var CAL_NAME = 'Bakery_Dasha';

function bakeryCalendar() {
  var list = CalendarApp.getCalendarsByName(CAL_NAME);
  return (list && list.length) ? list[0] : CalendarApp.getDefaultCalendar();
}

function doPost(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var d = {};
    if (e && e.postData && e.postData.contents) {
      d = JSON.parse(e.postData.contents);
    }

    if (sheet.getLastRow() === 0) {
      sheet.appendRow(['Date', 'Time', 'Event Date', 'People', 'Tiers', 'Decor',
                       'Delivery', 'Total Amount', 'Deposit', 'Client', 'Status']);
    }

    var tz = Session.getScriptTimeZone();
    var now = new Date();
    var dateStr = Utilities.formatDate(now, tz, 'dd.MM.yyyy');
    var timeStr = Utilities.formatDate(now, tz, 'HH:mm');

    var delivery = /достав/i.test(d.delivery || '') ? 'Delivery'
                 : (/самовыв|pickup/i.test(d.delivery || '') ? 'Pickup' : (d.delivery || ''));

    function money(v) {
      if (v === '' || v == null) return '';
      var n = parseInt(String(v).replace(/[^0-9]/g, ''), 10);
      if (isNaN(n)) return String(v);
      return '$' + n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    var statusMap = { confirmed: 'Confirmed', approved: 'Approved', quoted: 'Quoted' };
    var status = statusMap[(d.status || '').toLowerCase()] || (d.status || '');

    sheet.appendRow([
      dateStr, timeStr, d.event_date || '', d.persons || '', d.tiers || '', d.decor || '',
      delivery, money(d.sum), money(d.deposit), d.client || '', status
    ]);

    // бронь даты в календаре Bakery_Dasha
    try {
      if (d.event_date) {
        var p = String(d.event_date).split('.'); // DD.MM.YYYY
        if (p.length === 3) {
          var evDate = new Date(parseInt(p[2], 10), parseInt(p[1], 10) - 1, parseInt(p[0], 10));
          if (!isNaN(evDate.getTime())) {
            var title = '🎂 Cake: ' + (d.persons || '?') + ' guests — ' + (d.client || '');
            var desc = 'Guests: ' + (d.persons || '') +
                       '\nTiers: ' + (d.tiers || '') +
                       '\nDecor: ' + (d.decor || '') +
                       '\n' + delivery +
                       '\nTotal: ' + money(d.sum) +
                       '\nDeposit: ' + money(d.deposit) +
                       '\nClient: ' + (d.client || '') +
                       '\nChat: ' + (d.chat_id || '');
            bakeryCalendar().createAllDayEvent(title, evDate, { description: desc });
          }
        }
      }
    } catch (calErr) { /* календарь не должен ломать запись */ }

    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * GET:
 *   ?count=DD.MM.YYYY  → число подтверждённых заказов на эту дату (для лимита в n8n)
 *   без параметров     → "ok" (проверка, что endpoint жив)
 */
/**
 * ТЕСТ: запусти эту функцию в редакторе (Run) — она:
 *  1) вызовет запрос авторизации Календаря (нажми Authorize),
 *  2) создаст тестовое событие 20.07.2026,
 *  3) в логе (View → Logs) покажет, какой календарь реально используется.
 * Если в логе не "Bakery_Dasha" — значит имя календаря не совпадает.
 */
function testCalendar() {
  var cal = bakeryCalendar();
  Logger.log('Использую календарь: ' + cal.getName());
  cal.createAllDayEvent('🎂 ТЕСТ брони', new Date(2026, 6, 20), { description: 'проверка доступа' });
  Logger.log('Событие создано на 20.07.2026');
}

function doGet(e) {
  try {
    if (e && e.parameter && e.parameter.count) {
      var target = String(e.parameter.count).trim();
      var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
      var tz = Session.getScriptTimeZone();
      var data = sheet.getDataRange().getValues();
      var n = 0;
      for (var i = 1; i < data.length; i++) {
        var evd = data[i][2];   // Event Date
        var st = String(data[i][10] || ''); // Status
        var evdStr = (evd instanceof Date)
          ? Utilities.formatDate(evd, tz, 'dd.MM.yyyy')
          : String(evd).trim();
        if (evdStr === target && /confirm/i.test(st)) n++;
      }
      return ContentService.createTextOutput(String(n));
    }
  } catch (err) {
    return ContentService.createTextOutput('0');
  }
  return ContentService.createTextOutput('ok');
}
