//+------------------------------------------------------------------+
//|                                         NexusDataBridgeEA.mq5    |
//|                          Nexus Overlay AI - Data Bridge EA        |
//|                          Sends XAUUSD market data via file bridge |
//+------------------------------------------------------------------+
#property copyright "Nexus Overlay AI"
#property link      "https://nexus-overlay.ai"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

//--- Input parameters
input string   InpSymbol        = "XAUUSD";        // Symbol to monitor
input string   InpBridgeDir     = "NexusBridge";   // Bridge directory (under MQL5/Files)
input int      InpHeartbeatSec  = 5;               // Heartbeat interval (seconds)
input int      InpMaxCandles    = 100;             // Max candles to send per timeframe
input bool     InpSendTicks     = true;            // Send tick data
input bool     InpSendCandles   = true;            // Send closed candles
input bool     InpSendSymbolInfo= true;            // Send symbol info on start
input int      InpStaleSec      = 30;              // Stale data threshold (seconds)
input bool     InpUseHTTP       = false;           // Use HTTP push (else file bridge)
input string   InpHTTPHost      = "127.0.0.1";    // HTTP bridge host
input int      InpHTTPPort      = 8765;            // HTTP bridge port

//--- Timeframe array
ENUM_TIMEFRAMES Timeframes[] = {
   PERIOD_M1, PERIOD_M3, PERIOD_M5,
   PERIOD_M15, PERIOD_M30, PERIOD_H1, PERIOD_H4
};
string TimeframeNames[] = {
   "M1", "M3", "M5", "M15", "M30", "H1", "H4"
};

//--- State variables
datetime g_lastHeartbeat    = 0;
datetime g_lastTickTime     = 0;
ulong    g_sequence         = 0;
bool     g_connected        = false;
datetime g_lastCandleClose[];
int      g_fileHandle       = INVALID_HANDLE;
string   g_fullBridgePath   = "";
bool     g_bridgeInitialized= false;

//--- WinHTTP handles (for HTTP mode)
int      g_httpSession      = 0;
int      g_httpConnection   = 0;
bool     g_httpInitialized  = false;

//+------------------------------------------------------------------+
//| Expert initialization function                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   //--- Validate symbol
   if(SymbolSelect(InpSymbol, true) == 0)
   {
      PrintFormat("[NexusBridge] ERROR: Cannot select symbol %s, error=%d", InpSymbol, GetLastError());
      return(INIT_FAILED);
   }
   
   //--- Build bridge directory path
   g_fullBridgePath = InpBridgeDir + "\\";
   
   //--- Ensure bridge directory exists
   int folderCheck = FolderCreate(InpBridgeDir, FILE_COMMON);
   if(folderCheck == 0 && GetLastError() != 5018) // 5018 = folder already exists
   {
      PrintFormat("[NexusBridge] WARNING: Could not create bridge dir (may exist), error=%d", GetLastError());
   }
   
   //--- Initialize candle tracking array
   ArrayResize(g_lastCandleClose, ArraySize(Timeframes));
   ArrayInitialize(g_lastCandleClose, 0);
   
   //--- Initialize HTTP if needed
   if(InpUseHTTP)
   {
      if(!InitHTTP())
      {
         Print("[NexusBridge] WARNING: HTTP init failed, falling back to file bridge");
         InpUseHTTP = false; // Can't modify input at runtime, but local check below
      }
   }
   
   //--- Send symbol info immediately
   if(InpSendSymbolInfo)
   {
      SendSymbolInfo();
   }
   
   //--- Subscribe to tick events
   if(InpSendTicks)
   {
      SymbolSelect(InpSymbol, true);
   }
   
   g_connected = true;
   SendConnectionStatus("CONNECTED", "EA initialized successfully");
   
   PrintFormat("[NexusBridge] Initialized for %s, bridge=%s", InpSymbol, g_fullBridgePath);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                    |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   SendConnectionStatus("DISCONNECTED", "EA deinitialized, reason=" + IntegerToString(reason));
   
   //--- Close file handle
   if(g_fileHandle != INVALID_HANDLE)
      FileClose(g_fileHandle);
   
   //--- Close HTTP handles
   if(g_httpInitialized)
      DeinitHTTP();
   
   PrintFormat("[NexusBridge] Deinitialized, reason=%d", reason);
}

//+------------------------------------------------------------------+
//| Expert tick function                                               |
//+------------------------------------------------------------------+
void OnTick()
{
   datetime now = TimeCurrent();
   
   //--- Check for stale data
   if(g_lastTickTime > 0 && (now - g_lastTickTime) > InpStaleSec)
   {
      SendConnectionStatus("STALE", StringFormat("No ticks for %d seconds", now - g_lastTickTime));
   }
   
   //--- Send tick data
   if(InpSendTicks)
   {
      SendMarketTick();
      g_lastTickTime = now;
   }
   
   //--- Check for closed candles on all timeframes
   if(InpSendCandles)
   {
      CheckAndSendClosedCandles();
   }
   
   //--- Send heartbeat if due
   if((now - g_lastHeartbeat) >= InpHeartbeatSec)
   {
      SendHeartbeat();
      g_lastHeartbeat = now;
   }
}

//+------------------------------------------------------------------+
//| Timer function for periodic checks                                  |
//+------------------------------------------------------------------+
void OnTimer()
{
   //--- Additional periodic checks can go here
}

//+------------------------------------------------------------------+
//| Chart event handler                                                 |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   //--- Reserved for future interactive features
}

//+------------------------------------------------------------------+
//| Send MARKET_TICK message                                           |
//+------------------------------------------------------------------+
void SendMarketTick()
{
   MqlTick tick;
   if(!SymbolInfoTick(InpSymbol, tick))
   {
      PrintFormat("[NexusBridge] ERROR: Cannot get tick for %s, error=%d", InpSymbol, GetLastError());
      return;
   }
   
   int digits = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   double spread = SymbolInfoInteger(InpSymbol, SYMBOL_SPREAD) * SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
   
   string json = StringFormat(
      "{\"protocol_version\":\"1.0\","
      "\"message_type\":\"MARKET_TICK\","
      "\"sequence\":%I64u,"
      "\"symbol\":\"%s\","
      "\"timeframe\":\"TICK\","
      "\"timestamp\":\"%s\","
      "\"payload\":{"
         "\"bid\":%s,"
         "\"ask\":%s,"
         "\"last\":%s,"
         "\"volume\":%.2f,"
         "\"spread\":%s,"
         "\"bid_volume\":%.2f,"
         "\"ask_volume\":%.2f,"
         "\"flags\":%d"
      "}}",
      g_sequence, InpSymbol,
      TimeToString(tick.time_msc, TIME_DATE | TIME_SECONDS),
      DoubleToString(tick.bid, digits),
      DoubleToString(tick.ask, digits),
      DoubleToString(tick.last, digits),
      tick.volume_real,
      DoubleToString(spread, digits),
      tick.volume_real,
      tick.volume_real,
      (int)tick.flags
   );
   
   g_sequence++;
   SendMessage(json);
}

//+------------------------------------------------------------------+
//| Check and send closed candles for all timeframes                    |
//+------------------------------------------------------------------+
void CheckAndSendClosedCandles()
{
   for(int tf = 0; tf < ArraySize(Timeframes); tf++)
   {
      //--- Get the latest completed candle (index 1, since 0 is current)
      datetime candleTime = iTime(InpSymbol, Timeframes[tf], 1);
      if(candleTime == 0) continue;
      
      //--- Check if we already sent this candle
      if(candleTime == g_lastCandleClose[tf]) continue;
      
      //--- New closed candle detected
      SendCandleClosed(Timeframes[tf], TimeframeNames[tf], 1);
      g_lastCandleClose[tf] = candleTime;
      
      PrintFormat("[NexusBridge] Closed candle detected: %s %s", TimeframeNames[tf], 
                  TimeToString(candleTime, TIME_DATE | TIME_SECONDS));
   }
}

//+------------------------------------------------------------------+
//| Send CANDLE_CLOSED message                                         |
//+------------------------------------------------------------------+
void SendCandleClosed(ENUM_TIMEFRAMES tf, string tfName, int shift)
{
   int digits = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   
   double open  = iOpen(InpSymbol, tf, shift);
   double high  = iHigh(InpSymbol, tf, shift);
   double low   = iLow(InpSymbol, tf, shift);
   double close = iClose(InpSymbol, tf, shift);
   double vol   = (double)iVolume(InpSymbol, tf, shift);
   datetime t   = iTime(InpSymbol, tf, shift);
   
   //--- Get previous candle for comparison
   double prevClose = iClose(InpSymbol, tf, shift + 1);
   double bodySize = MathAbs(close - open);
   double range = high - low;
   double upperWick = high - MathMax(open, close);
   double lowerWick = MathMin(open, close) - low;
   
   //--- Determine candle pattern
   string pattern = "UNKNOWN";
   if(bodySize < range * 0.1)
      pattern = "DOJI";
   else if(close > open && lowerWick > bodySize * 2)
      pattern = "HAMMER";
   else if(close < open && upperWick > bodySize * 2)
      pattern = "SHOOTING_STAR";
   else if(close > open)
      pattern = "BULLISH";
   else
      pattern = "BEARISH";
   
   string json = StringFormat(
      "{\"protocol_version\":\"1.0\","
      "\"message_type\":\"CANDLE_CLOSED\","
      "\"sequence\":%I64u,"
      "\"symbol\":\"%s\","
      "\"timeframe\":\"%s\","
      "\"timestamp\":\"%s\","
      "\"payload\":{"
         "\"open\":%s,"
         "\"high\":%s,"
         "\"low\":%s,"
         "\"close\":%s,"
         "\"volume\":%.2f,"
         "\"candle_time\":\"%s\","
         "\"body_size\":%s,"
         "\"range\":%s,"
         "\"upper_wick\":%s,"
         "\"lower_wick\":%s,"
         "\"prev_close\":%s,"
         "\"pattern\":\"%s\""
      "}}",
      g_sequence, InpSymbol, tfName,
      TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
      DoubleToString(open, digits),
      DoubleToString(high, digits),
      DoubleToString(low, digits),
      DoubleToString(close, digits),
      vol,
      TimeToString(t, TIME_DATE | TIME_SECONDS),
      DoubleToString(bodySize, digits),
      DoubleToString(range, digits),
      DoubleToString(upperWick, digits),
      DoubleToString(lowerWick, digits),
      DoubleToString(prevClose, digits),
      pattern
   );
   
   g_sequence++;
   SendMessage(json);
}

//+------------------------------------------------------------------+
//| Send SYMBOL_INFO message (called once on init, or on request)      |
//+------------------------------------------------------------------+
void SendSymbolInfo()
{
   int digits      = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   double point    = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
   double spread   = SymbolInfoInteger(InpSymbol, SYMBOL_SPREAD) * point;
   double lotsMin  = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN);
   double lotsMax  = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX);
   double lotsStep = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP);
   double tickSize = SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_SIZE);
   double tickVal  = SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_VALUE);
   double contractSize = SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double swapLong = SymbolInfoDouble(InpSymbol, SYMBOL_SWAP_LONG);
   double swapShort= SymbolInfoDouble(InpSymbol, SYMBOL_SWAP_SHORT);
   long   stopLevel= SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_STOPS_LEVEL);
   long   freezeLevel = SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_FREEZE_LEVEL);
   string currency = SymbolInfoString(InpSymbol, SYMBOL_CURRENCY_BASE);
   string desc     = SymbolInfoString(InpSymbol, SYMBOL_DESCRIPTION);
   long   tradeMode= SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_MODE);
   
   MqlTick tick;
   SymbolInfoTick(InpSymbol, tick);
   
   string json = StringFormat(
      "{\"protocol_version\":\"1.0\","
      "\"message_type\":\"SYMBOL_INFO\","
      "\"sequence\":%I64u,"
      "\"symbol\":\"%s\","
      "\"timeframe\":\"INFO\","
      "\"timestamp\":\"%s\","
      "\"payload\":{"
         "\"digits\":%d,"
         "\"point\":%s,"
         "\"spread\":%s,"
         "\"lot_min\":%.2f,"
         "\"lot_max\":%.2f,"
         "\"lot_step\":%.2f,"
         "\"tick_size\":%s,"
         "\"tick_value\":%.6f,"
         "\"contract_size\":%.2f,"
         "\"swap_long\":%.6f,"
         "\"swap_short\":%.6f,"
         "\"stop_level\":%d,"
         "\"freeze_level\":%d,"
         "\"currency\":\"%s\","
         "\"description\":\"%s\","
         "\"trade_mode\":%d,"
         "\"last_bid\":%s,"
         "\"last_ask\":%s"
      "}}",
      g_sequence, InpSymbol,
      TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
      digits,
      DoubleToString(point, digits),
      DoubleToString(spread, digits),
      lotsMin, lotsMax, lotsStep,
      DoubleToString(tickSize, digits),
      tickVal,
      contractSize,
      swapLong, swapShort,
      stopLevel, freezeLevel,
      currency, desc, tradeMode,
      DoubleToString(tick.bid, digits),
      DoubleToString(tick.ask, digits)
   );
   
   g_sequence++;
   SendMessage(json);
}

//+------------------------------------------------------------------+
//| Send HEARTBEAT message                                             |
//+------------------------------------------------------------------+
void SendHeartbeat()
{
   //--- Gather current state
   long memUsed = 0;
   MqlTick lastTick;
   SymbolInfoTick(InpSymbol, lastTick);
   
   int digits = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   int spread = (int)SymbolInfoInteger(InpSymbol, SYMBOL_SPREAD);
   
   //--- Build candle age for each timeframe
   string candleAges = "";
   for(int tf = 0; tf < ArraySize(Timeframes); tf++)
   {
      datetime lastClose = iTime(InpSymbol, Timeframes[tf], 1);
      int ageSec = (int)(TimeCurrent() - lastClose);
      if(tf > 0) candleAges += ",";
      candleAges += StringFormat("\"%s\":%d", TimeframeNames[tf], ageSec);
   }
   
   string json = StringFormat(
      "{\"protocol_version\":\"1.0\","
      "\"message_type\":\"HEARTBEAT\","
      "\"sequence\":%I64u,"
      "\"symbol\":\"%s\","
      "\"timeframe\":\"HEART\","
      "\"timestamp\":\"%s\","
      "\"payload\":{"
         "\"status\":\"ALIVE\","
         "\"bid\":%s,"
         "\"ask\":%s,"
         "\"spread\":%d,"
         "\"uptime_ticks\":%I64u,"
         "\"candle_ages\":{%s},"
         "\"memory_used\":%d"
      "}}",
      g_sequence, InpSymbol,
      TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
      DoubleToString(lastTick.bid, digits),
      DoubleToString(lastTick.ask, digits),
      spread,
      g_sequence,
      candleAges,
      memUsed
   );
   
   g_sequence++;
   SendMessage(json);
}

//+------------------------------------------------------------------+
//| Send CONNECTION_STATUS message                                     |
//+------------------------------------------------------------------+
void SendConnectionStatus(string status, string message)
{
   string json = StringFormat(
      "{\"protocol_version\":\"1.0\","
      "\"message_type\":\"CONNECTION_STATUS\","
      "\"sequence\":%I64u,"
      "\"symbol\":\"%s\","
      "\"timeframe\":\"STAT\","
      "\"timestamp\":\"%s\","
      "\"payload\":{"
         "\"status\":\"%s\","
         "\"message\":\"%s\","
         "\"mt5_build\":%d,"
         "\"ea_version\":\"1.00\","
         "\"bridge_mode\":\"%s\""
      "}}",
      g_sequence, InpSymbol,
      TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
      status, message,
      TerminalInfoInteger(TERMINAL_BUILD),
      InpUseHTTP ? "HTTP" : "FILE"
   );
   
   g_sequence++;
   SendMessage(json);
}

//+------------------------------------------------------------------+
//| Send message via configured transport                               |
//+------------------------------------------------------------------+
void SendMessage(string json)
{
   //--- Add checksum (simple length-based for validation)
   int checksum = StringLen(json);
   //--- Insert checksum before last brace
   int lastBrace = StringFind(json, "}}");
   if(lastBrace > 0)
   {
      json = StringSubstr(json, 0, lastBrace) + 
             ",\"checksum\":" + IntegerToString(checksum) + 
             StringSubstr(json, lastBrace);
   }
   
   if(InpUseHTTP)
   {
      SendViaHTTP(json);
   }
   else
   {
      SendViaFile(json);
   }
}

//+------------------------------------------------------------------+
//| Send message via file bridge                                        |
//+------------------------------------------------------------------+
void SendViaFile(string json)
{
   //--- Write to a unique file (timestamp-based)
   string filename = g_fullBridgePath + "msg_" + 
                     TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + 
                     "_" + IntegerToString(g_sequence) + ".json";
   
   //--- Replace colons in filename for Windows compatibility
   StringReplace(filename, ":", "");
   StringReplace(filename, " ", "_");
   
   int handle = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("[NexusBridge] ERROR: Cannot write file %s, error=%d", filename, GetLastError());
      return;
   }
   
   FileWriteString(handle, json);
   FileClose(handle);
   
   //--- Also write/update the latest pointer file
   string latestFile = g_fullBridgePath + "latest.json";
   handle = FileOpen(latestFile, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(handle != INVALID_HANDLE)
   {
      FileWriteString(handle, json);
      FileClose(handle);
   }
}

//+------------------------------------------------------------------+
//| Send message via HTTP push                                         |
//+------------------------------------------------------------------+
void SendViaHTTP(string json)
{
   if(!g_httpInitialized)
   {
      if(!InitHTTP()) return;
   }
   
   //--- Use WinHTTP API
   string url = "/message";
   string headers = "Content-Type: application/json\r\n";
   
   uchar data[];
   int dataLen = StringLen(json);
   ArrayResize(data, dataLen);
   for(int i = 0; i < dataLen; i++)
      data[i] = (uchar)StringGetCharacter(json, i);
   
   int request = HttpOpenRequestW(g_httpConnection, "POST", url, 
                                   "HTTP/1.1", NULL, NULL, 
                                   INTERNET_FLAG_RELOAD, 0);
   if(request == 0)
   {
      PrintFormat("[NexusBridge] ERROR: HttpOpenRequest failed, error=%d", 
                  (int)GetLastError());
      g_httpInitialized = false;
      return;
   }
   
   bool sent = HttpSendRequestW(request, headers, StringLen(headers), 
                                 data, dataLen);
   if(!sent)
   {
      PrintFormat("[NexusBridge] ERROR: HttpSendRequest failed, error=%d",
                  (int)GetLastError());
   }
   
   InternetCloseHandle(request);
}

//+------------------------------------------------------------------+
//| Initialize WinHTTP session and connection                          |
//+------------------------------------------------------------------+
bool InitHTTP()
{
   g_httpSession = InternetOpenW("NexusDataBridge/1.0", 
                                  INTERNET_OPEN_TYPE_PRECONFIG,
                                  NULL, NULL, 0);
   if(g_httpSession == 0)
   {
      PrintFormat("[NexusBridge] ERROR: InternetOpen failed, error=%d", 
                  (int)GetLastError());
      return false;
   }
   
   g_httpConnection = InternetConnectW(g_httpSession,
                                        StringToWChar(InpHTTPHost),
                                        (ushort)InpHTTPPort,
                                        NULL, NULL,
                                        INTERNET_SERVICE_HTTP,
                                        0, 0);
   if(g_httpConnection == 0)
   {
      PrintFormat("[NexusBridge] ERROR: InternetConnect failed to %s:%d, error=%d",
                  InpHTTPHost, InpHTTPPort, (int)GetLastError());
      InternetCloseHandle(g_httpSession);
      g_httpSession = 0;
      return false;
   }
   
   g_httpInitialized = true;
   PrintFormat("[NexusBridge] HTTP connected to %s:%d", InpHTTPHost, InpHTTPPort);
   return true;
}

//+------------------------------------------------------------------+
//| Deinitialize WinHTTP                                               |
//+------------------------------------------------------------------+
void DeinitHTTP()
{
   if(g_httpConnection != 0)
   {
      InternetCloseHandle(g_httpConnection);
      g_httpConnection = 0;
   }
   if(g_httpSession != 0)
   {
      InternetCloseHandle(g_httpSession);
      g_httpSession = 0;
   }
   g_httpInitialized = false;
}

//+------------------------------------------------------------------+
//| Helper: convert string to wchart (simplified)                      |
//+------------------------------------------------------------------+
ushort StringToWChar(string str)
{
   if(StringLen(str) == 0) return 0;
   return (ushort)StringGetCharacter(str, 0);
}
//+------------------------------------------------------------------+
