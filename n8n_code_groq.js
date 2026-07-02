// ═══════════════════════════════════════════════════════════════════════
//  Code-нода «Консьерж: бриф + цена» — ОДИН бот, маршрутизация клиент↔Даша
//  Клиент пишет боту → карточка Даше (admin) → Даша жмёт ✅ → ответ клиенту.
//  Куда: n8n → нода «Консьерж: бриф + цена» → Cmd+A → вставить этот код.
//  Mode: Run Once for All Items, Language: JavaScript.
//
//  ЗАПОЛНИ 4 СТРОКИ НИЖЕ:
//   1) BOT_TOKEN      — токен бота от @BotFather (для отправки клиенту).
//   2) ADMIN_CHAT_ID  — chat_id Даши (куда шлём карточки на аппрув). Узнать: @userinfobot.
//                       Оставишь пусто — карточка придёт тому же, кто написал (соло-демо).
//   3) GROQ_KEY       — ключ gsk_... (без него — регулярки).
//   4) LOG_URL        — URL Google Apps Script (пусто — не пишет в базу).
//
//  Нода сама делает все отправки в Telegram и возвращает [] — узел «Карточка Даше»
//  после неё ничего не шлёт (у него нет входных элементов). Это норма.
// ═══════════════════════════════════════════════════════════════════════

const BOT_TOKEN = 'PASTE_BOT_TOKEN';
const ADMIN_CHAT_ID = '';
const GROQ_KEY = 'PASTE_YOUR_GROQ_KEY_HERE';
const GROQ_MODEL = 'llama-3.3-70b-versatile';
const LOG_URL = 'PASTE_APPS_SCRIPT_WEB_APP_URL';

const upd = $input.first().json;
const NL = String.fromCharCode(10);
const TG = 'https://api.telegram.org/bot' + BOT_TOKEN;

// отправка в Telegram напрямую (кнопки — только для карточки Даши)
const send = async (chat, text, buttons, parseMode) => {
  const body = { chat_id: chat, text: text };
  if (buttons) body.reply_markup = { inline_keyboard: buttons };
  if (parseMode) body.parse_mode = parseMode;
  try { await this.helpers.httpRequest({ method: 'POST', url: TG + '/sendMessage', body: body, json: true }); }
  catch (e) { /* не роняем флоу из-за одной отправки */ }
};
const adminButtons = [[
  { text: '✅ Approve', callback_data: 'approve' },
  { text: '✏️ Edit', callback_data: 'edit' },
  { text: '❌ Decline', callback_data: 'reject' }
]];

// ─────────────────────────────────────────────────────────────
// ТАП ПО КНОПКЕ (Даша в admin-чате)
// ─────────────────────────────────────────────────────────────
if (upd.callback_query) {
  const cbData = upd.callback_query.data || '';
  const card = (upd.callback_query.message && upd.callback_query.message.text) ? upd.callback_query.message.text : '';
  const adminChat = upd.callback_query.message.chat.id;
  const cid = (card.match(/#cid:(-?[0-9]+)/) || [])[1] || '';
  const parts = card.split('Draft to client:');
  const draft = parts.length > 1 ? parts[1].trim() : '';

  if (cbData === 'approve') {
    if (cid && draft) await send(cid, draft, null);      // quote to the CLIENT
    // remember the client's order until they confirm (DB write happens at confirm)
    if (cid) {
      const grab = (re) => { const m = card.match(re); return m ? m[1] : ''; };
      const sd = $getWorkflowStaticData('global');
      sd['ord_' + cid] = {
        event_date: grab(/([0-9]{2}\.[0-9]{2}\.[0-9]{4})/),
        persons: grab(/([0-9]+)\s*guest/),
        tiers: grab(/([0-9]+)\s*tier/),
        decor: grab(/decor:\s*(\S+)/),
        delivery: /Delivery/.test(card) ? 'Delivery' : (/Pickup/.test(card) ? 'Pickup' : ''),
        sum: grab(/TOTAL:\s*\$?([0-9]+)/),
        deposit: grab(/deposit\s*\$?([0-9]+)/)
      };
    }
    await send(adminChat, '✅ Quote sent to the client. Waiting for their confirmation.', null);
  } else if (cbData === 'reject') {
    await send(adminChat, '❌ Declined — nothing was sent to the client.', null);
  } else {
    await send(adminChat, '✏️ OK, edit the draft and send it to the client manually.', null);
  }
  return [];
}

// ─────────────────────────────────────────────────────────────
// СООБЩЕНИЕ ОТ КЛИЕНТА
// ─────────────────────────────────────────────────────────────
const msg = (upd.message && upd.message.text) ? upd.message.text : '';
const customerChat = upd.message ? upd.message.chat.id : null;
const custFrom = (upd.message && upd.message.from) ? upd.message.from : {};
const custName = custFrom.username ? ('@' + custFrom.username) : (custFrom.first_name || ('tg:' + customerChat));
const admin = (ADMIN_CHAT_ID && /^-?[0-9]+$/.test(String(ADMIN_CHAT_ID))) ? ADMIN_CHAT_ID : customerChat;
const today = new Date();
const lang = /[а-яё]/i.test(msg) ? 'ru' : 'en';   // есть кириллица → русский, иначе английский
const L = (ru, en) => (lang === 'en' ? en : ru);

const WELCOME = 'Привет! 🎂 Я помощник пекарни Даши. Напишите, какой торт нужен — на сколько человек, на какую дату, пожелания по вкусу и оформлению — и я подготовлю расчёт.' + NL + NL + 'Hi! 🎂 I\'m Dasha\'s bakery assistant. Tell me about the cake — how many people, the date, flavor and design preferences — and I\'ll prepare a quote.';
if (msg.indexOf('/start') === 0) {
  await send(customerChat, WELCOME, null);
  return [];
}

// приветствие без заказа → тёплый welcome (как /start)
const lowStart = msg.trim().toLowerCase();
const isGreeting = /^(привет|здравствуй|здрасьте|добрый день|добрый вечер|доброе утро|хай|hi|hello|hey|good morning|good afternoon|good evening|good day|салют|здаров|ку)/.test(lowStart);
const orderSignalEarly = /[0-9]/.test(lowStart) || /(торт|тортик|заказ|человек|персон|ярус|начин|доставк|самовывоз|cake|order|people|guest|tier|deliver)/.test(lowStart);
if (isGreeting && !orderSignalEarly) {
  await send(customerChat, WELCOME, null);
  return [];
}

function toDate(s){ if(!s) return null; const p=String(s).split('-'); if(p.length!==3) return null; const d=new Date(+p[0],+p[1]-1,+p[2]); return isNaN(d.getTime())?null:d; }
function fmt(d){ const p=n=>n<10?('0'+n):(''+n); return p(d.getDate())+'.'+p(d.getMonth()+1)+'.'+d.getFullYear(); }

let a = null;
let engine = 'регулярки';
const SYSTEM = 'Ты ассистент пекарни кастомных тортов. Клиент может писать по-русски или по-английски — понимай оба языка одинаково. Верни ТОЛЬКО JSON без пояснений: {"message_type":"order|sensitive|smalltalk|confirm","servings":число|null,"event_date":"YYYY-MM-DD"|null,"tiers":число,"decor":"simple|medium|complex","delivery":true|false}. Сегодня ' + today.toISOString().slice(0,10) + ', год 2026. message_type=confirm если клиент СОГЛАШАЕТСЯ/подтверждает уже озвученный заказ (да, давай, давайте, согласна, подтверждаю, беру, оплачу, договорились, го; англ.: yes, agree, confirm, sure, deal, book it, ok, let\'s do it). message_type=sensitive для жалоб и тяжёлых тем. message_type=smalltalk для благодарностей и фраз без заказа. decor=complex если фигурки/роспись/динозавр/золочение/лепка; medium если цвета/ягоды/надпись/тема; иначе simple. Относительные даты (завтра/tomorrow, в субботу/on saturday, через неделю) переводи в конкретную YYYY-MM-DD. Не выдумывай отсутствующее — ставь null.';

if (GROQ_KEY.indexOf('gsk_') === 0) {
  try {
    const resp = await this.helpers.httpRequest({
      method: 'POST',
      url: 'https://api.groq.com/openai/v1/chat/completions',
      headers: { 'Authorization': 'Bearer ' + GROQ_KEY, 'Content-Type': 'application/json' },
      body: { model: GROQ_MODEL, temperature: 0, messages: [ { role: 'system', content: SYSTEM }, { role: 'user', content: msg } ] },
      json: true
    });
    let content = String(resp.choices[0].message.content).trim();
    content = content.replace(/^```json/i, '').replace(/^```/, '').replace(/```$/, '').trim();
    const d = JSON.parse(content);
    a = { message_type: d.message_type || 'order', servings: d.servings || null, event_date: toDate(d.event_date), tiers: d.tiers || 1, decor: d.decor || 'simple', delivery: !!d.delivery };
    engine = 'Groq';
  } catch (e) { a = null; }
}

if (!a) {
  const low = msg.toLowerCase();
  const SENS = ['жалоб','кисл','испорт','ужасн','верните','возврат','похорон','соболезн','болезн','расстроен','недоволен'];
  const CONFIRM = ['согласн','подтвержда','беру','оформля','договорил','оплач','устраивает','подходит'];
  const enConfirm = /\b(yes|yeah|yep|agree|confirm|sure|deal|okay|ok|book it|sounds good|perfect)\b/i.test(msg);
  if (SENS.some(w => low.indexOf(w) !== -1)) {
    a = { message_type: 'sensitive' };
  } else if (CONFIRM.some(w => low.indexOf(w) !== -1) || enConfirm) {
    a = { message_type: 'confirm' };
  } else {
    let servings = null;
    let m1 = low.match(/([0-9]{1,3})\s*(?:человек|персон|гост|чел|people|person|persons|guest|guests|pax|ppl)/);
    if (m1) servings = parseInt(m1[1]);
    else { let m2 = low.match(/(?:человек|персон|гост|гостей|чел|people|person|guest)[а-яa-z]*\s*([0-9]{1,3})/); if (m2) servings = parseInt(m2[1]); }
    const MONTHS = {'январ':1,'феврал':2,'март':3,'апрел':4,'ма':5,'июн':6,'июл':7,'август':8,'сентябр':9,'октябр':10,'ноябр':11,'декабр':12,'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12};
    const MONTHRE = '(январ|феврал|март|апрел|ма|июн|июл|август|сентябр|октябр|ноябр|декабр|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)';
    let ev = null;
    let dm = low.match(new RegExp('([0-9]{1,2})[ .]*' + MONTHRE));
    let dm2 = dm ? null : low.match(new RegExp(MONTHRE + '[a-zа-я]*\\s+([0-9]{1,2})'));
    if (dm) { const day = +dm[1]; const mo = MONTHS[dm[2]]; const y = (today.getMonth()+1) <= mo ? today.getFullYear() : today.getFullYear()+1; ev = new Date(y, mo-1, day); }
    else if (dm2) { const day = +dm2[2]; const mo = MONTHS[dm2[1]]; const y = (today.getMonth()+1) <= mo ? today.getFullYear() : today.getFullYear()+1; ev = new Date(y, mo-1, day); }
    else { let dd = low.match(/([0-9]{1,2})[.\/]([0-9]{1,2})/); if (dd) ev = new Date(today.getFullYear(), +dd[2]-1, +dd[1]); }
    const COMPLEX = ['фигур','динозавр','роспис','золот','объёмн','лепк','figure','dinosaur','gold','sculpt','3d'];
    const MEDIUM = ['цвет','ягод','надпис','декор','тема','color','berr','text','theme','decor'];
    let decor = 'simple';
    if (COMPLEX.some(w => low.indexOf(w) !== -1)) decor = 'complex';
    else if (MEDIUM.some(w => low.indexOf(w) !== -1)) decor = 'medium';
    a = { message_type: 'order', servings, event_date: ev, tiers: (/(ярус|tier)/.test(low) ? 2 : 1), decor, delivery: ['достав','привез','адрес','deliver'].some(w => low.indexOf(w) !== -1) };
  }
}

// ── чувствительное → Даше (человеку), клиенту мягкий ack ──
if (a.message_type === 'sensitive') {
  await send(admin, '🙋 SENSITIVE from client (chat ' + customerChat + ') — reply personally:' + NL + '«' + msg + '»' + NL + '#cid:' + customerChat, null);
  await send(customerChat, L('Спасибо, что написали 🙏 Даша ответит вам лично совсем скоро.', 'Thank you for your message 🙏 Dasha will reply to you personally very soon.'), null);
  return [];
}

// ── защита от петли: короткие «супер/жду/спасибо» без сигналов заказа — не заказ ──
const lowMsg = msg.toLowerCase();
const hasOrderSignal = /[0-9]/.test(lowMsg) || /(торт|тортик|заказ|человек|персон|ярус|начин|доставк|самовывоз|cake|order|people|guest|tier|deliver)/.test(lowMsg);
if (a.message_type === 'order' && !a.servings && !a.event_date && !hasOrderSignal) {
  a.message_type = 'smalltalk';
}

// короткое «давай / да / ок / go / sure» без деталей заказа = подтверждение, а не болтовня
if (a.message_type === 'smalltalk' && /^(давай(те)?|да|ага|окей|ок|го|погнали|конечно|yes|yeah|yep|ok|okay|sure|deal|let'?s|go)([\s.,!?]|$)/i.test(msg.trim())) {
  a.message_type = 'confirm';
}

// ── клиент подтвердил заказ → сумма предоплаты + запись в базу (всегда) ──
if (a.message_type === 'confirm') {
  const sd = $getWorkflowStaticData('global');
  const ord = sd['ord_' + customerChat] || {};
  const dep = ord.deposit || '';

  if (dep) {
    await send(customerChat, L(
      'Ваш заказ принят! 🎂 Чтобы забронировать дату, внесите предоплату $' + dep + '. Мы свяжемся с вами за день до события, чтобы подтвердить все детали. Спасибо, что выбрали нас! 🙌',
      'Your order is confirmed! 🎂 To reserve the date, please make a prepayment of $' + dep + '. We\'ll contact you the day before your event to confirm all the details. Thank you for choosing us! 🙌'), null);
  } else {
    await send(customerChat, L(
      'Ваш заказ принят! 🎂 Мы свяжемся с вами за день до события, чтобы подтвердить детали и сумму предоплаты. Спасибо! 🙌',
      'Your order is confirmed! 🎂 We\'ll contact you the day before your event to confirm the details and the prepayment amount. Thank you! 🙌'), null);
  }

  // строку в таблицу пишем ВСЕГДА (контакт клиента + что нашли в памяти)
  if (LOG_URL.indexOf('http') === 0) {
    try {
      await this.helpers.httpRequest({ method: 'POST', url: LOG_URL, body: {
        event_date: ord.event_date || '', persons: ord.persons || '', tiers: ord.tiers || '',
        decor: ord.decor || '', delivery: ord.delivery || '', sum: ord.sum || '', deposit: dep,
        client: custName, chat_id: String(customerChat), status: 'confirmed'
      }, json: true });
    } catch (e) {}
  }

  await send(admin, '✅ ' + custName + ' (chat ' + customerChat + ') confirmed the order' + (dep ? (', deposit $' + dep) : '') + '.' + NL + '🗂 Saved to the database.', null);
  if (sd['ord_' + customerChat]) delete sd['ord_' + customerChat];
  return [];
}

// ── благодарности / общие фразы → дружелюбный ответ, без петли ──
if (a.message_type === 'smalltalk') {
  await send(customerChat, L(
    'Спасибо! 😊 Если захотите торт — просто опишите: на сколько человек, на какую дату и пожелания по оформлению.',
    'Thank you! 😊 Whenever you\'d like a cake, just describe it: how many people, the date, and any design wishes.'), null);
  return [];
}

// ── не хватает данных → уточнение КЛИЕНТУ (без кнопок) ──
if (!a.servings || !a.event_date) {
  const need = [];
  if (!a.servings) need.push(L('число персон', 'number of guests'));
  if (!a.event_date) need.push(L('дату', 'the date'));
  await send(customerChat, L(
    'Обожаю такие заказы! 😊 Подскажите, пожалуйста, ' + need.join(' и ') + '?',
    'Love these orders! 😊 Could you tell me ' + need.join(' and ') + '?'), null);
  return [];
}

// ── цена (детерминированно) ──
function basePrice(s){ const t=[[8,60],[15,95],[25,150],[40,240]]; for (let i=0;i<t.length;i++){ if (s<=t[i][0]) return t[i][1]; } return Math.round(240*s/40); }
const tiers = a.tiers || 1;
const base = basePrice(a.servings);
const tiersExtra = 50*Math.max(0, tiers-1);
const decorAdd = a.decor==='complex'?90:(a.decor==='medium'?40:0);
const deliveryAdd = a.delivery?25:0;
const subtotal = base+tiersExtra+decorAdd+deliveryAdd;
const daysUntil = Math.round((a.event_date - today)/(1000*60*60*24));
const isRush = daysUntil < 4;
const rush = isRush ? Math.round(subtotal*0.30) : 0;
const total = subtotal+rush;
const deposit = Math.round(total*0.5);

const maxSaneTiers = Math.max(2, Math.ceil(a.servings/8));
const tierWarn = (tiers > maxSaneTiers) ? ('<b>⚠️ CHECK: ' + tiers + ' tiers for ' + a.servings + ' guests — looks like a mistake/joke.</b>' + NL + NL) : '';

// ── лимит на день: реальный подсчёт подтверждённых заказов на эту дату (из таблицы) ──
const DAILY_LIMIT = 3;
let dayCount = 0;
if (LOG_URL.indexOf('http') === 0) {
  try {
    const rr = await this.helpers.httpRequest({ method: 'GET', url: LOG_URL + '?count=' + encodeURIComponent(fmt(a.event_date)) });
    dayCount = parseInt(String(rr).replace(/[^0-9]/g, ''), 10) || 0;
  } catch (e) { dayCount = 0; }
}
const dayFull = dayCount >= DAILY_LIMIT;
const dayWarn = dayFull
  ? ('<b>⚠️ DAY FULL: ' + fmt(a.event_date) + ' already has ' + dayCount + ' cakes (limit ' + DAILY_LIMIT + '). Decide manually whether you can take another one.</b>' + NL + NL)
  : '';

// ── карточка заказа Даше (решение всегда за ней; при полном дне — с предупреждением) ──
const draft = L(
  'Обожаю такие заказы! 🎂 На ' + a.servings + ' человек к ' + fmt(a.event_date) + ' сделаю — выйдет $' + total + ' (предоплата $' + deposit + ' бронирует дату). Подтверждаем? 😊',
  'Love this order! 🎂 For ' + a.servings + ' people by ' + fmt(a.event_date) + ' — it will be $' + total + ' (a $' + deposit + ' deposit reserves the date). Shall we confirm? 😊');
let lines = 'Base: $' + base;
if (tiersExtra) lines += NL + 'Extra tiers: +$' + tiersExtra;
if (decorAdd) lines += NL + 'Decor: +$' + decorAdd;
if (deliveryAdd) lines += NL + 'Delivery: +$' + deliveryAdd;
if (isRush) lines += NL + 'Rush (+30%): +$' + rush;
lines += NL + 'TOTAL: $' + total + ' (deposit $' + deposit + ')';
const custNameH = custName.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const cardText = '#cid:' + customerChat + NL + dayWarn + tierWarn + 'NEW ORDER  [' + engine + '·' + lang + ']' + NL + '👤 ' + custNameH + NL + a.servings + ' guests · ' + fmt(a.event_date) + ' · ' + tiers + ' tier · decor: ' + a.decor + ' · ' + (a.delivery?'Delivery':'Pickup') + NL + NL + lines + NL + NL + 'On ' + fmt(a.event_date) + ': ' + dayCount + '/' + DAILY_LIMIT + ' orders' + NL + NL + 'Draft to client:' + NL + draft;
await send(admin, cardText, adminButtons, 'HTML');
await send(customerChat, L('Спасибо! 🙌 Уже готовлю расчёт — вернусь с подтверждением совсем скоро.', 'Thank you! 🙌 I\'m preparing your quote — I\'ll get back to you very soon.'), null);
return [];
