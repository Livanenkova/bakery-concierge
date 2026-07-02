"""
Генерирует готовый к импорту workflow-JSON для n8n: Telegram Trigger → Code → карточка.
Обходит баг API-создания (500 на Telegram-ноде): импорт в UI использует Telegram-ноду
твоей версии. Запуск:  python3 build_n8n_workflow.py  → создаст dasha_concierge.n8n.json
"""
import json, uuid

JS_CODE = """const upd = $input.first().json;
const NL = String.fromCharCode(10);
const chatId = upd.callback_query ? upd.callback_query.message.chat.id : (upd.message ? upd.message.chat.id : null);

if (upd.callback_query) {
  const data = upd.callback_query.data || '';
  let t;
  if (data === 'approve') t = 'Готово — ответ отправлен клиенту (демо). Дата забронирована.';
  else if (data === 'reject') t = 'Отклонено — клиенту ничего не ушло.';
  else t = 'Ок, открой черновик, поправь и отправь вручную.';
  return [{ json: { chatId: chatId, text: t } }];
}

const msg = (upd.message && upd.message.text) ? upd.message.text : '';
const low = msg.toLowerCase();
const today = new Date();

const SENS = ['жалоб','кисл','испорт','ужасн','верните','возврат','похорон','соболезн','болезн','расстроен','недоволен'];
if (SENS.some(function(w){ return low.indexOf(w) !== -1; })) {
  const t = 'ТОЛЬКО ДЛЯ ТЕБЯ — не автоматизирую.' + NL + 'Клиент прислал чувствительное сообщение (жалоба/тяжёлая тема).' + NL + 'Я не пишу черновик — ответь, пожалуйста, лично.';
  return [{ json: { chatId: chatId, text: t } }];
}

let servings = null;
let m1 = low.match(/([0-9]{1,3})[ ]*(?:человек|персон|гост|чел)/);
if (m1) servings = parseInt(m1[1]);
else { let m2 = low.match(/(?:человек|персон|гост|гостей|чел)[а-я]*[ ]*([0-9]{1,3})/); if (m2) servings = parseInt(m2[1]); }

const MONTHS = {'январ':1,'феврал':2,'март':3,'апрел':4,'ма':5,'июн':6,'июл':7,'август':8,'сентябр':9,'октябр':10,'ноябр':11,'декабр':12};
let ev = null;
let dm = low.match(/([0-9]{1,2})[ .]*(январ|феврал|март|апрел|ма|июн|июл|август|сентябр|октябр|ноябр|декабр)/);
if (dm) {
  const day = parseInt(dm[1]); const mo = MONTHS[dm[2]];
  const y = (today.getMonth()+1) <= mo ? today.getFullYear() : today.getFullYear()+1;
  ev = new Date(y, mo-1, day);
} else {
  let dd = low.match(/([0-9]{1,2})[.]([0-9]{1,2})/);
  if (dd) ev = new Date(today.getFullYear(), parseInt(dd[2])-1, parseInt(dd[1]));
}

const COMPLEX = ['фигур','динозавр','роспис','золот','объёмн','лепк'];
const MEDIUM = ['цвет','ягод','надпис','декор','тема'];
let decor = 'simple';
if (COMPLEX.some(function(w){ return low.indexOf(w)!==-1; })) decor='complex';
else if (MEDIUM.some(function(w){ return low.indexOf(w)!==-1; })) decor='medium';
const tiers = (low.indexOf('ярус')!==-1) ? 2 : 1;
const delivery = ['достав','привез','адрес'].some(function(w){ return low.indexOf(w)!==-1; });

function fmt(d){ const p=function(n){ return n<10?('0'+n):(''+n); }; return p(d.getDate())+'.'+p(d.getMonth()+1)+'.'+d.getFullYear(); }

if (!servings || !ev) {
  const need = [];
  if (!servings) need.push('число персон');
  if (!ev) need.push('дату');
  const t = 'Не хватает данных для расчёта: ' + need.join(', ') + '.' + NL + 'Черновик уточнения клиенту: Обожаю такие заказы! Подскажи, пожалуйста, ' + need.join(' и ') + '?';
  return [{ json: { chatId: chatId, text: t } }];
}

function basePrice(s){ const t=[[8,2500],[15,4000],[25,6000],[40,9000]]; for (let i=0;i<t.length;i++){ if (s<=t[i][0]) return t[i][1]; } return Math.round(9000*s/40); }
const base = basePrice(servings);
const tiersExtra = 2000*Math.max(0,tiers-1);
const decorAdd = decor==='complex'?3500:(decor==='medium'?1500:0);
const deliveryAdd = delivery?800:0;
const subtotal = base+tiersExtra+decorAdd+deliveryAdd;
const daysUntil = Math.round((ev - today)/(1000*60*60*24));
const isRush = daysUntil < 4;
const rush = isRush ? Math.round(subtotal*0.30) : 0;
const total = subtotal+rush;
const deposit = Math.round(total*0.5);

const dd2 = (ev.getDay()+6)%7;
const mon = new Date(ev); mon.setDate(ev.getDate()-dd2);
const sun = new Date(mon); sun.setDate(mon.getDate()+6);
const BOOKED = ['2026-07-14'];
const booked = BOOKED.map(function(s){ return new Date(s); }).filter(function(d){ return d>=mon && d<=sun; }).length;
const hasRoom = booked < 6;

if (!hasRoom) {
  const draft = 'Ой, спасибо, что подумали обо мне! Но на эту неделю я уже полностью расписана и не хочу делать ваш торт наспех. Могу поставить в лист ожидания или испечь к ближайшей свободной дате — как вам?';
  const t = 'ВНИМАНИЕ: неделя ' + fmt(mon) + ' — ' + fmt(sun) + ' ПОЛНАЯ (' + booked + '/6).' + NL + 'Рекомендую: отказ + вейтлист (не бери наспех).' + NL + NL + 'Черновик отказа:' + NL + draft;
  return [{ json: { chatId: chatId, text: t } }];
}

const draft = 'Обожаю такие заказы! На ' + servings + ' человек к ' + fmt(ev) + ' сделаю — выйдет ' + total + ' руб (предоплата ' + deposit + ' руб бронирует дату). Подтверждаем?';
let lines = 'База: ' + base + ' руб';
if (tiersExtra) lines += NL + 'Доп. ярусы: +' + tiersExtra + ' руб';
if (decorAdd) lines += NL + 'Декор: +' + decorAdd + ' руб';
if (deliveryAdd) lines += NL + 'Доставка: +' + deliveryAdd + ' руб';
if (isRush) lines += NL + 'Срочность (+30%): +' + rush + ' руб';
lines += NL + 'ИТОГО: ' + total + ' руб (предоплата ' + deposit + ' руб)';
const t = 'НОВЫЙ ЗАКАЗ' + NL + servings + ' перс. · ' + fmt(ev) + ' · декор: ' + decor + ' · ' + (delivery?'доставка':'самовывоз') + NL + NL + lines + NL + NL + 'Неделя ' + fmt(mon) + ' — ' + fmt(sun) + ': ' + booked + '/6 (место есть)' + NL + NL + 'Черновик ответа клиенту:' + NL + draft;
return [{ json: { chatId: chatId, text: t } }];"""

trigger_id = str(uuid.uuid4())
code_id = str(uuid.uuid4())
send_id = str(uuid.uuid4())

nodes = [
    {
        "parameters": {"updates": ["message", "callback_query"], "additionalFields": {}},
        "id": trigger_id,
        "name": "Входящее сообщение",
        "type": "n8n-nodes-base.telegramTrigger",
        "typeVersion": 1.2,
        "position": [240, 300],
        "webhookId": str(uuid.uuid4()),
    },
    {
        "parameters": {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": JS_CODE},
        "id": code_id,
        "name": "Консьерж: бриф + цена",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [540, 300],
    },
    {
        "parameters": {
            "resource": "message",
            "operation": "sendMessage",
            "chatId": "={{ $json.chatId }}",
            "text": "={{ $json.text }}",
            "replyMarkup": "inlineKeyboard",
            "inlineKeyboard": {"rows": [{"row": {"buttons": [
                {"text": "✅ Одобрить", "additionalFields": {"callback_data": "approve"}},
                {"text": "✏️ Изменить", "additionalFields": {"callback_data": "edit"}},
                {"text": "❌ Отклонить", "additionalFields": {"callback_data": "reject"}},
            ]}}]},
            "additionalFields": {"appendAttribution": False},
        },
        "id": send_id,
        "name": "Карточка Даше",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [840, 300],
    },
]

connections = {
    "Входящее сообщение": {"main": [[{"node": "Консьерж: бриф + цена", "type": "main", "index": 0}]]},
    "Консьерж: бриф + цена": {"main": [[{"node": "Карточка Даше", "type": "main", "index": 0}]]},
}

wf = {
    "name": "Консьерж заказов Даши",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
}

with open("dasha_concierge.n8n.json", "w", encoding="utf-8") as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)

print("Готово: dasha_concierge.n8n.json —", len(json.dumps(wf)), "байт,", len(nodes), "ноды")
