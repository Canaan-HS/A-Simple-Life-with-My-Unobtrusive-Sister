/* ============================================================
 * 設定
 * ============================================================ */

const CONFIG = {
  SOURCE_ID: "1vEwhXk3hnKIIV1fydbuR_gXMHufDQICj", // 來源試算表，全程只讀，不會被修改
  AUTH_TOKEN: "xxx", // 'xxx' = 不啟用；帶對 token 可跳過限流
  RATE_LIMIT: { limit: 5, windowSeconds: 3600 },
  LOCK_WAIT_MS: 300000, // 重建期間，其他請求最多排隊等待的時間

  FOLDER_NAME: "Imouto_Guide_Cache", // Drive 內存放成品與暫存的資料夾
  TEMP_PREFIX: "Tmp:", // 暫存副本檔名前綴

  CLEAN: {
    dropEmptyColumns: "all", // 'all' | 'trailing' | 'none'
    dropEmptyRows: "trailing", // 'all' | 'trailing' | 'none'
    protectImages: false, // true = 保留圖片錨點所在的列欄（多一次 SpreadsheetApp 讀取，較慢）
  },

  ZIP: {
    imageExts: [
      "jpg",
      "jpeg",
      "png",
      "gif",
      "bmp",
      "webp",
      "avif",
      "heic",
      "svg",
    ],
    htmlPattern: /\.html?$/i,
  },
};

const MIME_XLSX =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const MIME_ZIP = "application/zip";

/* ============================================================
 * 請求入口
 * ============================================================ */

function doGet(e) {
  try {
    const params = (e && e.parameter) || {};
    const action = params.action;

    if (!action) return jsonOut_({ error: "missing_action" });
    if (!Object.prototype.hasOwnProperty.call(ACTIONS, action)) {
      return jsonOut_({ error: "unknown_action", action: action });
    }

    // token 只決定是否跳過限流；不帶或帶錯一律放行但吃限流
    const authed =
      CONFIG.AUTH_TOKEN !== "xxx" && params.token === CONFIG.AUTH_TOKEN;
    if (!authed) {
      const rate = checkRate_(action);
      if (!rate.ok) {
        return jsonOut_({
          error: "rate_limited",
          retry_after: rate.retry_after,
          limit: CONFIG.RATE_LIMIT.limit,
          window_seconds: CONFIG.RATE_LIMIT.windowSeconds,
        });
      }
    }
    return jsonOut_(ACTIONS[action]());
  } catch (err) {
    return jsonOut_({
      error: "internal_error",
      message: String((err && err.message) || err),
    });
  }
}

function jsonOut_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON,
  );
}

/* ============================================================
 * 限流
 * ============================================================ */

function checkRate_(action) {
  const key = "rate:" + action;
  const cache = CacheService.getScriptCache();
  const now = Date.now();
  const { limit, windowSeconds } = CONFIG.RATE_LIMIT;

  let count = 0,
    expiry = 0;
  const raw = cache.get(key);
  if (raw) {
    const p = raw.split(":");
    count = parseInt(p[0], 10) || 0;
    expiry = parseInt(p[1], 10) || 0;
  }
  if (now >= expiry) {
    count = 0;
    expiry = now + windowSeconds * 1000;
  }
  if (count >= limit) {
    return {
      ok: false,
      retry_after: Math.max(1, Math.ceil((expiry - now) / 1000)),
    };
  }
  cache.put(key, count + 1 + ":" + expiry, 21600);
  return { ok: true };
}

/* ============================================================
 * 基礎工具
 * ============================================================ */

// 帶 OAuth token、不因 HTTP 錯誤拋例外；由呼叫方檢查狀態碼
function http_(url, options) {
  return UrlFetchApp.fetch(
    url,
    Object.assign(
      {
        headers: { Authorization: "Bearer " + ScriptApp.getOAuthToken() },
        muteHttpExceptions: true,
      },
      options || {},
    ),
  );
}

// 接受字串或位元組陣列，回傳 hex
function sha256_(input) {
  const digest =
    typeof input === "string"
      ? Utilities.computeDigest(
          Utilities.DigestAlgorithm.SHA_256,
          input,
          Utilities.Charset.UTF_8,
        )
      : Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, input);
  return digest
    .map((b) => ((b & 0xff) < 0x10 ? "0" : "") + (b & 0xff).toString(16))
    .join("");
}

/* ============================================================
 * 來源讀取（唯讀）
 * ============================================================ */

function sourceInfo_() {
  const file = DriveApp.getFileById(CONFIG.SOURCE_ID);
  return { stamp: file.getLastUpdated().getTime(), name: file.getName() };
}

// kind: 'xlsx' | 'zip'；先走 docs 匯出，失敗再走 Drive API
function fetchExport_(spreadsheetId, kind) {
  const mime = kind === "xlsx" ? MIME_XLSX : MIME_ZIP;
  const urls = [
    "https://docs.google.com/spreadsheets/d/" +
      spreadsheetId +
      "/export?format=" +
      kind,
    "https://www.googleapis.com/drive/v3/files/" +
      spreadsheetId +
      "/export?mimeType=" +
      encodeURIComponent(mime),
  ];
  const codes = [];
  for (let i = 0; i < urls.length; i++) {
    const res = http_(urls[i]);
    codes.push(res.getResponseCode());
    if (res.getResponseCode() === 200) {
      const blob = res.getBlob();
      const b = blob.getBytes();
      // 檢查 zip 檔頭 "PK"（xlsx 本質也是 zip）
      if (b.length >= 2 && b[0] === 0x50 && b[1] === 0x4b) {
        return blob.setContentType(MIME_ZIP);
      }
    }
  }
  throw new Error(kind + " 匯出失敗: " + codes.join(" / "));
}

/* ============================================================
 * 儲存層：Drive 資料夾操作（所有寫入與刪除的唯一出口）
 * ============================================================ */

const Store = {
  folder() {
    const it = DriveApp.getFoldersByName(CONFIG.FOLDER_NAME);
    return it.hasNext() ? it.next() : DriveApp.createFolder(CONFIG.FOLDER_NAME);
  },

  byName(name) {
    const out = [];
    const it = Store.folder().getFilesByName(name);
    while (it.hasNext()) {
      const f = it.next();
      if (!f.isTrashed()) out.push(f);
    }
    return out;
  },

  // 暫存副本：來源只被讀取；指定 mimeType 讓 Drive 在複製時轉成原生 Google 試算表
  copyTemp(sourceId, name) {
    const created = Drive.Files.copy(
      {
        name: CONFIG.TEMP_PREFIX + name,
        mimeType: "application/vnd.google-apps.spreadsheet",
        parents: [Store.folder().getId()],
      },
      sourceId,
      { supportsAllDrives: true },
    );
    return DriveApp.getFileById(created.id);
  },

  // 清掉殘留暫存（上次執行逾時中斷時會留下）
  sweepTemp() {
    const it = Store.folder().getFiles();
    while (it.hasNext()) {
      const f = it.next();
      if (f.getName().indexOf(CONFIG.TEMP_PREFIX) === 0) Store.trash(f);
    }
  },

  // 唯一的刪除出口：絕不刪來源，且只刪快取資料夾內的檔案
  trash(file) {
    if (file.getId() === CONFIG.SOURCE_ID)
      throw new Error("拒絕修改原始試算表");
    const parents = file.getParents();
    if (
      !parents.hasNext() ||
      parents.next().getId() !== Store.folder().getId()
    ) {
      throw new Error("拒絕刪除非快取資料夾內的檔案");
    }
    file.setTrashed(true);
  },
};

/* ============================================================
 * 後端：相同介面
 *   get(key)               → { meta, read() } | null
 *   put(key, data, meta)
 *   remove(key)
 * ============================================================ */

// 小型 JSON：指令碼屬性（永久；單值上限約 9KB）
const PropsBackend = {
  get(key) {
    const raw = PropertiesService.getScriptProperties().getProperty(key);
    if (!raw) return null;
    try {
      const obj = JSON.parse(raw);
      return { meta: obj.meta, read: () => obj.data };
    } catch (err) {
      return null;
    }
  },
  put(key, data, meta) {
    PropertiesService.getScriptProperties().setProperty(
      key,
      JSON.stringify({ meta: meta, data: data }),
    );
  },
  remove(key) {
    PropertiesService.getScriptProperties().deleteProperty(key);
  },
};

// 大型檔案：Drive 資料夾；meta 存在檔案描述欄，檢查新鮮度時不必下載內容
const DriveBackend = {
  get(name) {
    const file = Store.byName(name)[0];
    if (!file) return null;
    let meta = null;
    try {
      meta = JSON.parse(file.getDescription());
    } catch (err) {}
    return { meta: meta, read: () => file.getBlob() };
  },
  // 先建新檔再刪舊檔，中途失敗也不會變成沒有檔案
  put(name, blob, meta) {
    const olds = Store.byName(name);
    const file = Store.folder().createFile(blob.setName(name));
    file.setDescription(JSON.stringify(meta));
    olds.forEach(Store.trash);
  },
  remove(name) {
    Store.byName(name).forEach(Store.trash);
  },
};

/* ============================================================
 * 通用快取器
 *   spec: {
 *     key, backend,
 *     version: 字串 或 () → 字串（建議用函式，請求時才求值）,
 *     build(src) → payload,
 *     respond(payload, src) → 回應物件
 *   }
 *   新鮮度只看：modifiedTime + 檔名 + 版本
 *   流程：新鮮 → 直接回；否則 取鎖 → 再檢查 → build → 存檔 → 回
 * ============================================================ */

const CACHES = [];

function defineCache_(spec) {
  CACHES.push(spec);
  return function () {
    const src = sourceInfo_(); // 先讀時間戳再 build：build 期間來源被改，下次請求會自動重建
    const version =
      typeof spec.version === "function" ? spec.version() : spec.version;

    const hit = spec.backend.get(spec.key);
    if (isFresh_(hit, src, version)) return spec.respond(hit.read(), src);

    return withLock_(() => {
      const again = spec.backend.get(spec.key);
      if (isFresh_(again, src, version)) return spec.respond(again.read(), src);

      const payload = spec.build(src);
      spec.backend.put(spec.key, payload, {
        version: version,
        stamp: src.stamp,
        name: src.name,
      });
      return spec.respond(payload, src);
    });
  };
}

function isFresh_(entry, src, version) {
  const m = entry && entry.meta;
  return !!(
    m &&
    m.version === version &&
    m.stamp === src.stamp &&
    m.name === src.name
  );
}

function withLock_(fn) {
  const lock = LockService.getScriptLock();
  lock.waitLock(CONFIG.LOCK_WAIT_MS);
  try {
    return fn();
  } finally {
    lock.releaseLock();
  }
}

// 把一組函式的原始碼雜湊成短版本號；任何一個函式內容改了，版本就變
function codeVersion_(fns) {
  return sha256_(fns.map((f) => f.toString()).join("\n")).slice(0, 8);
}

/* ============================================================
 * 功能：get_meta
 *   modifiedTime 沒變 → 回傳屬性中的快取
 *   有變 → 下載 xlsx，在記憶體內計算語意雜湊（不經過你的雲端）
 * ============================================================ */

const getMeta_ = defineCache_({
  key: "META",
  version: () =>
    codeVersion_([
      analyzeXlsx_,
      sheetSignature_,
      parseStyles_,
      parseSharedStrings_,
      parseWorkbook_,
      attr_,
      all_,
      unescapeXml_,
    ]),
  backend: PropsBackend,
  build: (src) => {
    const a = analyzeXlsx_(fetchExport_(CONFIG.SOURCE_ID, "xlsx"));
    return { name: src.name, hash: a.hash, sheets: a.sheets };
  },
  respond: (payload) => payload,
});

/* ---------- 語意雜湊：Google 每次匯出會重新編號 shared string 與 style 索引，
 *            所以比對解析後的語意（值、樣式、欄寬列高、合併），而非 XML 位元組 ---------- */

function analyzeXlsx_(xlsxBlob) {
  const files = {};
  Utilities.unzip(xlsxBlob).forEach((e) => {
    files[e.getName()] = e;
  });
  const text = (p) => (files[p] ? files[p].getDataAsString("UTF-8") : "");

  const shared = parseSharedStrings_(text("xl/sharedStrings.xml"));
  const styles = parseStyles_(text("xl/styles.xml"));
  const defs = parseWorkbook_(
    text("xl/workbook.xml"),
    text("xl/_rels/workbook.xml.rels"),
  );

  const digests = defs.map((d) =>
    sha256_(sheetSignature_(d.name, text(d.path), shared, styles)),
  );
  return { hash: sha256_(digests.join("|")), sheets: defs.map((d) => d.name) };
}

/* ---------- XML 小工具 ---------- */

function unescapeXml_(s) {
  return String(s).replace(
    /&(lt|gt|quot|apos|amp|#\d+|#x[0-9a-fA-F]+);/g,
    (m, g) => {
      if (g === "lt") return "<";
      if (g === "gt") return ">";
      if (g === "quot") return '"';
      if (g === "apos") return "'";
      if (g === "amp") return "&";
      return String.fromCharCode(
        g[1] === "x" ? parseInt(g.slice(2), 16) : parseInt(g.slice(1), 10),
      );
    },
  );
}

function attr_(tag, name) {
  const m = new RegExp("(?:^|\\s)" + name + '="([^"]*)"').exec(tag);
  return m ? unescapeXml_(m[1]) : "";
}

function all_(re, s, fn) {
  const out = [];
  let m;
  while ((m = re.exec(s)) !== null) out.push(fn(m));
  return out;
}

/* ---------- workbook / sharedStrings / styles ---------- */

function parseWorkbook_(wbXml, relsXml) {
  const rels = {};
  all_(/<Relationship\b[^>]*>/g, relsXml, (m) => {
    let target = attr_(m[0], "Target");
    target = target.charAt(0) === "/" ? target.slice(1) : "xl/" + target;
    rels[attr_(m[0], "Id")] = target;
  });
  return all_(/<sheet\b[^>]*>/g, wbXml, (m) => ({
    name: attr_(m[0], "name"),
    path: rels[attr_(m[0], "r:id")],
  }));
}

function parseSharedStrings_(xml) {
  return all_(/<si\b[^>]*>([\s\S]*?)<\/si>/g, xml, (m) => {
    const body = m[1].replace(/<rPh\b[\s\S]*?<\/rPh>/g, ""); // 去掉注音
    return all_(/<t\b[^>]*>([\s\S]*?)<\/t>/g, body, (t) =>
      unescapeXml_(t[1]),
    ).join("");
  });
}

// 回傳 xf 索引 → 語意簽章（不含索引本身）
function parseStyles_(xml) {
  const block = (tag) => {
    const m = new RegExp(
      "<" + tag + "\\b[^>]*>([\\s\\S]*?)</" + tag + ">",
    ).exec(xml);
    return m ? m[1] : "";
  };
  const color = (s) => {
    const m = /<(?:color|fgColor)\b[^>]*>/.exec(s);
    return m
      ? [
          attr_(m[0], "rgb"),
          attr_(m[0], "theme"),
          attr_(m[0], "indexed"),
          attr_(m[0], "tint"),
        ].join(",")
      : "";
  };

  const numFmts = {};
  all_(/<numFmt\b[^>]*>/g, block("numFmts"), (m) => {
    numFmts[attr_(m[0], "numFmtId")] = attr_(m[0], "formatCode");
  });

  const fonts = all_(
    /<font>([\s\S]*?)<\/font>|<font\/>/g,
    block("fonts"),
    (m) => {
      const b = m[1] || "";
      const val = (tag) => {
        const t = new RegExp("<" + tag + "\\b[^>]*>").exec(b);
        return t ? attr_(t[0], "val") : "";
      };
      return [
        val("name"),
        val("sz"),
        /<b\b/.test(b),
        /<i\b/.test(b),
        color(b),
      ].join(",");
    },
  );

  const fills = all_(/<fill>([\s\S]*?)<\/fill>/g, block("fills"), (m) => {
    const p = /<patternFill\b[^>]*>/.exec(m[1]);
    return (p ? attr_(p[0], "patternType") : "") + "," + color(m[1]);
  });

  return all_(
    /<xf\b([^>]*?)(?:\/>|>([\s\S]*?)<\/xf>)/g,
    block("cellXfs"),
    (m) => {
      const id = attr_(m[1], "numFmtId");
      const al = /<alignment\b[^>]*>/.exec(m[2] || "");
      return [
        numFmts[id] !== undefined ? numFmts[id] : "builtin:" + id,
        fonts[parseInt(attr_(m[1], "fontId"), 10)] || "",
        fills[parseInt(attr_(m[1], "fillId"), 10)] || "",
        al
          ? [
              attr_(al[0], "horizontal"),
              attr_(al[0], "vertical"),
              attr_(al[0], "wrapText"),
            ].join(",")
          : "",
      ].join("\x00");
    },
  );
}

/* ---------- 單張工作表簽章 ---------- */

function sheetSignature_(name, xml, shared, styles) {
  const out = [name];

  all_(/<col\b[^>]*>/g, xml, (m) => {
    out.push(
      "col" +
        [
          attr_(m[0], "min"),
          attr_(m[0], "max"),
          attr_(m[0], "width"),
          attr_(m[0], "hidden"),
        ].join(","),
    );
  });
  all_(/<row\b[^>]*>/g, xml, (m) => {
    const ht = attr_(m[0], "ht"),
      hidden = attr_(m[0], "hidden");
    if (ht || hidden)
      out.push("row" + attr_(m[0], "r") + "=" + ht + "," + hidden);
  });

  all_(/<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g, xml, (m) => {
    const s = attr_(m[1], "s") || "0";
    const t = attr_(m[1], "t");
    const body = m[2] || "";
    let value = "";
    if (t === "s") {
      const v = /<v>([\s\S]*?)<\/v>/.exec(body);
      value = v ? shared[parseInt(v[1], 10)] : "";
    } else if (t === "inlineStr") {
      value = all_(/<t\b[^>]*>([\s\S]*?)<\/t>/g, body, (x) =>
        unescapeXml_(x[1]),
      ).join("");
    } else {
      const v = /<v>([\s\S]*?)<\/v>/.exec(body);
      value = v ? unescapeXml_(v[1]) : "";
    }
    if (value === "" && s === "0") return; // 空且無樣式才略過（空但有樣式會影響 HTML class）
    out.push(
      attr_(m[1], "r") +
        "\x00" +
        (t === "s" || t === "inlineStr" ? "s" : t || "n") +
        "\x00" +
        value +
        "\x00" +
        (styles[parseInt(s, 10)] || ""),
    );
  });

  out.push(
    "merge:" +
      all_(/<mergeCell\b[^>]*>/g, xml, (m) => attr_(m[0], "ref"))
        .sort()
        .join(","),
  );
  return out.join("\n");
}

/* ============================================================
 * 功能：export_zip
 *   modifiedTime 沒變 → 回傳 Drive 內的成品
 *   有變 → 暫存副本 → 清洗 → 匯出 → 處理 → 存成品 → 刪暫存
 * ============================================================ */

const exportZip_ = defineCache_({
  key: "export.zip", // Drive 內的檔名
  version: () =>
    codeVersion_([
      buildZip_,
      processZip_,
      hasImageExtension_,
      cleanSpreadsheet_,
      collectImageAnchors_,
      planClean_,
      planDrop_,
      buildDeleteRequests_,
    ]) +
    "|" +
    JSON.stringify(CONFIG.CLEAN) +
    "|" +
    JSON.stringify(CONFIG.ZIP.imageExts) +
    "|" +
    String(CONFIG.ZIP.htmlPattern),
  backend: DriveBackend,
  build: buildZip_,
  // ContentService 無法直接回傳二進位，改回傳 base64
  respond: (blob, src) => {
    const bytes = blob.getBytes();
    return {
      name: src.name,
      modified: src.stamp,
      size: bytes.length,
      zip_base64: Utilities.base64Encode(bytes),
    };
  },
});

function buildZip_(src) {
  Store.sweepTemp();
  const temp = Store.copyTemp(CONFIG.SOURCE_ID, src.name);
  try {
    cleanSpreadsheet_(temp.getId());
    return processZip_(fetchExport_(temp.getId(), "zip"), src.name);
  } finally {
    try {
      Store.trash(temp);
    } catch (err) {}
  }
}

function processZip_(zipBlob, name) {
  const kept = [];
  Utilities.unzip(zipBlob).forEach((entry) => {
    const path = entry.getName();
    if (!path || path.endsWith("/") || hasImageExtension_(path)) return;

    if (CONFIG.ZIP.htmlPattern.test(path)) {
      // Google 匯出的是不含 DOCTYPE 的片段，缺少會讓瀏覽器進入 quirks mode
      const text = entry
        .getDataAsString("UTF-8")
        .replace(/^\s*<!DOCTYPE[^>]*>\s*/i, "");
      kept.push(
        Utilities.newBlob("<!DOCTYPE html>\n" + text, "text/html", path),
      );
    } else {
      kept.push(entry);
    }
  });
  return Utilities.zip(kept, name);
}

function hasImageExtension_(path) {
  const dot = path.lastIndexOf(".");
  return (
    dot >= 0 &&
    CONFIG.ZIP.imageExts.indexOf(path.slice(dot + 1).toLowerCase()) !== -1
  );
}

/* ============================================================
 * 暫存副本清洗：一次讀、一次寫（只作用於暫存副本）
 * ============================================================ */

function cleanSpreadsheet_(id) {
  if (id === CONFIG.SOURCE_ID) throw new Error("拒絕修改原始試算表");

  const fields =
    "sheets(properties(sheetId,gridProperties(rowCount,columnCount))," +
    "merges,data(rowData(values(formattedValue))))";
  const grid = Sheets.Spreadsheets.get(id, {
    includeGridData: true,
    fields: fields,
  });
  const anchors = CONFIG.CLEAN.protectImages ? collectImageAnchors_(id) : {};

  let requests = [];
  (grid.sheets || []).forEach((sheet) => {
    const sheetId = sheet.properties.sheetId;
    requests = requests.concat(
      buildDeleteRequests_(sheetId, planClean_(sheet, anchors[sheetId] || [])),
    );
  });
  if (requests.length === 0) return;

  Sheets.Spreadsheets.batchUpdate({ requests: requests }, id);
}

// 圖片錨點所在的列欄要保留（Sheets API 不提供，只能用 SpreadsheetApp）
function collectImageAnchors_(id) {
  const out = {};
  SpreadsheetApp.openById(id)
    .getSheets()
    .forEach((sheet) => {
      out[sheet.getSheetId()] = sheet
        .getImages()
        .map((img) => img.getAnchorCell())
        .filter(Boolean)
        .map((cell) => [cell.getRow() - 1, cell.getColumn() - 1]);
    });
  return out;
}

// 回傳要刪除的 0-based 列欄索引
function planClean_(sheet, anchors) {
  const rowCount = sheet.properties.gridProperties.rowCount;
  const colCount = sheet.properties.gridProperties.columnCount;
  const rowData = (sheet.data && sheet.data[0] && sheet.data[0].rowData) || [];

  const keepRow = new Array(rowCount).fill(false);
  const keepCol = new Array(colCount).fill(false);
  const hasText = (r, c) => {
    const cells = rowData[r] && rowData[r].values;
    const v = cells && cells[c] && cells[c].formattedValue;
    return v !== undefined && v !== null && String(v).trim() !== "";
  };

  // 有文字的儲存格
  rowData.forEach((row, r) => {
    (row.values || []).forEach((_, c) => {
      if (hasText(r, c)) {
        keepRow[r] = true;
        keepCol[c] = true;
      }
    });
  });

  // 左上角有文字的合併：涵蓋的列欄保留
  (sheet.merges || []).forEach((m) => {
    const r0 = m.startRowIndex || 0,
      r1 = m.endRowIndex || 0;
    const c0 = m.startColumnIndex || 0,
      c1 = m.endColumnIndex || 0;
    if (!hasText(r0, c0)) return;
    for (let r = r0; r < r1 && r < rowCount; r++) keepRow[r] = true;
    for (let c = c0; c < c1 && c < colCount; c++) keepCol[c] = true;
  });

  // 圖片錨點
  anchors.forEach((a) => {
    if (a[0] >= 0 && a[0] < rowCount) keepRow[a[0]] = true;
    if (a[1] >= 0 && a[1] < colCount) keepCol[a[1]] = true;
  });

  return {
    cols: planDrop_(keepCol, CONFIG.CLEAN.dropEmptyColumns),
    rows: planDrop_(keepRow, CONFIG.CLEAN.dropEmptyRows),
  };
}

// keep: 布林陣列；mode: 'all' | 'trailing' | 'none'；回傳要刪的索引（至少留一個）
function planDrop_(keep, mode) {
  if (mode === "none") return [];
  const drop = [];
  const from = mode === "trailing" ? keep.lastIndexOf(true) + 1 : 0;
  for (let i = from; i < keep.length; i++) {
    if (mode === "trailing" || !keep[i]) drop.push(i);
  }
  if (drop.length === keep.length) drop.shift(); // Sheets API 不允許刪光
  return drop;
}

// 連續索引合併成區間，由後往前刪避免位移
function buildDeleteRequests_(sheetId, plan) {
  const make = (dimension, indexes) => {
    const ranges = [];
    indexes.forEach((i) => {
      const last = ranges[ranges.length - 1];
      if (last && last.end === i) last.end = i + 1;
      else ranges.push({ start: i, end: i + 1 });
    });
    return ranges.reverse().map((r) => ({
      deleteDimension: {
        range: {
          sheetId: sheetId,
          dimension: dimension,
          startIndex: r.start,
          endIndex: r.end,
        },
      },
    }));
  };
  return make("COLUMNS", plan.cols).concat(make("ROWS", plan.rows));
}

/* ============================================================
 * 動作登錄表
 * ============================================================ */

const ACTIONS = {
  get_meta: getMeta_,
  export_zip: exportZip_,
};

/* ============================================================
 * 編輯器內測試 與 維護工具
 * ============================================================ */

function testGetMeta() {
  runTest_("get_meta", 3000);
}
function testExportZip() {
  runTest_("export_zip", 200);
}

function runTest_(action, sliceLen) {
  const t = Date.now();
  const out = doGet({
    parameter: { action: action, token: CONFIG.AUTH_TOKEN },
  });
  Logger.log("耗時 " + formatDuration_(Date.now() - t));
  Logger.log(out.getContent().slice(0, sliceLen));
}

// 毫秒 → 秒；滿 60 秒改用「分 秒」顯示
function formatDuration_(ms) {
  const total = Math.round(ms / 1000);
  if (ms < 60000) return (ms / 1000).toFixed(2) + " 秒";
  return Math.floor(total / 60) + " 分 " + (total % 60) + " 秒";
}

// 連續匯出兩次，確認語意雜湊穩定
function diagHashStability() {
  const a = analyzeXlsx_(fetchExport_(CONFIG.SOURCE_ID, "xlsx"));
  Utilities.sleep(3000);
  const b = analyzeXlsx_(fetchExport_(CONFIG.SOURCE_ID, "xlsx"));
  Logger.log(
    a.hash === b.hash
      ? "穩定：兩次雜湊相同"
      : "不穩定：\n" + a.hash + "\n" + b.hash,
  );
}

// 一鍵清除所有快取與暫存（不碰來源），並清掉舊版殘留的屬性
function resetAll() {
  CACHES.forEach((c) => c.backend.remove(c.key));
  Store.sweepTemp();
}
