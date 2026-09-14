//+------------------------------------------------------------------+
//|                                      NexusOverlayIndicator.mq5   |
//|                          Nexus Overlay AI - Signal Overlay        |
//|                          Reads signals from Python backend file   |
//+------------------------------------------------------------------+
#property copyright "Nexus Overlay AI"
#property link      "https://nexus-overlay.ai"
#property version   "1.00"
#property strict
#property indicator_chart_window
#property indicator_buffers 5
#property indicator_plots   0

//--- Input parameters
input string   InpSignalFile   = "nexus_signals.json";  // Signal file name
input string   InpSignalDir    = "NexusSignals";         // Signal directory
input bool     InpShowEntry    = true;                   // Show Entry lines
input bool     InpShowSL       = true;                   // Show Stop Loss lines
input bool     InpShowTP       = true;                   // Show TP lines (TP1/TP2/TP3)
input bool     InpShowZones    = true;                   // Show S/R zones
input bool     InpShowLabels   = true;                   // Show signal labels
input bool     InpShowMarkers  = true;                   // Show signal markers
input bool     InpAutoScroll   = true;                   // Auto-scroll to latest
input color    InpBuyColor     = clrLime;                // Buy color
input color    InpSellColor    = clrRed;                 // Sell color
input color    InpWaitColor    = clrGold;                // Wait color
input color    InpSLColor      = clrOrangeRed;           // SL line color
input color    InpTP1Color     = clrMediumSeaGreen;      // TP1 color
input color    InpTP2Color     = clrDodgerBlue;          // TP2 color
input color    InpTP3Color     = clrDarkOrchid;          // TP3 color
input color    InpSupportColor = clrCadetBlue;           // Support zone color
input color    InpResistColor  = clrIndianRed;           // Resistance zone color
input int      InpFontSize     = 10;                     // Label font size
input ENUM_LINE_STYLE InpLineStyle = STYLE_SOLID;        // Line style
input int      InpLineWidth    = 2;                      // Line width

//--- Indicator buffers (unused but required for compilation)
double Buffer1[];
double Buffer2[];
double Buffer3[];
double Buffer4[];
double Buffer5[];

//--- Object name prefixes
#define PREFIX_ENTRY   "NexusEntry_"
#define PREFIX_SL      "NexusSL_"
#define PREFIX_TP1     "NexusTP1_"
#define PREFIX_TP2     "NexusTP2_"
#define PREFIX_TP3     "NexusTP3_"
#define PREFIX_LABEL   "NexusLabel_"
#define PREFIX_MARKER  "NexusMarker_"
#define PREFIX_ZONE    "NexusZone_"
#define PREFIX_SUFFIX  "_override"

//--- Signal data structure
struct SignalData
{
   string   signal_type;    // BUY, SELL, WAIT
   double   entry_price;
   double   stop_loss;
   double   tp1;
   double   tp2;
   double   tp3;
   datetime signal_time;
   string   timeframe;
   double   confidence;
   string   reason;
};

//--- Signal storage
SignalData g_currentSignal;
datetime   g_lastFileTime    = 0;
bool       g_signalValid     = false;
int        g_fileHandle      = INVALID_HANDLE;

//+------------------------------------------------------------------+
//| Custom indicator initialization function                           |
//+------------------------------------------------------------------+
int OnInit()
{
   //--- Set indicator buffers
   SetIndexBuffer(0, Buffer1);
   SetIndexBuffer(1, Buffer2);
   SetIndexBuffer(2, Buffer3);
   SetIndexBuffer(3, Buffer4);
   SetIndexBuffer(4, Buffer5);
   
   //--- Set indicator name
   IndicatorSetString(INDICATOR_SHORTNAME, "Nexus Overlay");
   
   //--- Ensure signal directory exists
   FolderCreate(InpSignalDir, FILE_COMMON);
   
   PrintFormat("[NexusOverlay] Initialized, watching: %s\\%s", InpSignalDir, InpSignalFile);
   
   EventSetMillisecondTimer(250); // Update 4x per second
   
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Custom indicator deinitialization function                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   //--- Remove all created objects
   ObjectsDeleteAll(0, PREFIX_ENTRY);
   ObjectsDeleteAll(0, PREFIX_SL);
   ObjectsDeleteAll(0, PREFIX_TP1);
   ObjectsDeleteAll(0, PREFIX_TP2);
   ObjectsDeleteAll(0, PREFIX_TP3);
   ObjectsDeleteAll(0, PREFIX_LABEL);
   ObjectsDeleteAll(0, PREFIX_MARKER);
   ObjectsDeleteAll(0, PREFIX_ZONE);
   
   EventKillTimer();
   
   Print("[NexusOverlay] Deinitialized, objects cleaned up");
}

//+------------------------------------------------------------------+
//| Timer handler - check for signal updates                           |
//+------------------------------------------------------------------+
void OnTimer()
{
   //--- Check if signal file has been updated
   if(CheckSignalFileUpdate())
   {
      //--- Remove old objects
      ClearOverlayObjects();
      
      //--- Draw new signal
      if(g_signalValid)
      {
         DrawSignalOverlay();
      }
   }
   
   //--- Redraw even if no update (price lines move)
   if(g_signalValid)
   {
      UpdatePriceLinePositions();
   }
}

//+------------------------------------------------------------------+
//| Custom indicator iteration function (required but unused)          |
//+------------------------------------------------------------------+
int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[],
                const double &close[], const long &tick_volume[],
                const long &volume[], const int &spread[])
{
   return(rates_total);
}

//+------------------------------------------------------------------+
//| Check if signal file has been updated                              |
//+------------------------------------------------------------------+
bool CheckSignalFileUpdate()
{
   string fullPath = InpSignalDir + "\\" + InpSignalFile;
   
   int handle = FileOpen(fullPath, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(handle == INVALID_HANDLE)
   {
      //--- Try alternate path with common flag
      handle = FileOpen(InpSignalFile, FILE_READ | FILE_TXT | FILE_ANSI);
      if(handle == INVALID_HANDLE)
         return false;
   }
   
   //--- Get file modification time
   datetime fileTime = (datetime)FileGetInteger(handle, FILE_MODIFY_DATE);
   if(fileTime == g_lastFileTime)
   {
      FileClose(handle);
      return false;
   }
   
   g_lastFileTime = fileTime;
   
   //--- Read entire file
   string content = "";
   while(!FileIsEnding(handle))
   {
      content += FileReadString(handle);
   }
   FileClose(handle);
   
   if(StringLen(content) == 0) return false;
   
   //--- Parse JSON (manual parsing for MQL5)
   return ParseSignalJSON(content);
}

//+------------------------------------------------------------------+
//| Parse signal JSON (simplified manual parser for MQL5)              |
//+------------------------------------------------------------------+
bool ParseSignalJSON(string json)
{
   //--- Extract fields using StringFind and StringSubstr
   g_signalValid = false;
   
   //--- Signal type
   g_currentSignal.signal_type = ExtractJSONString(json, "signal");
   if(g_currentSignal.signal_type == "") 
   {
      g_currentSignal.signal_type = ExtractJSONString(json, "signal_type");
   }
   if(g_currentSignal.signal_type == "") return false;
   
   //--- Prices
   g_currentSignal.entry_price = ExtractJSONDouble(json, "entry");
   g_currentSignal.stop_loss   = ExtractJSONDouble(json, "sl");
   g_currentSignal.tp1         = ExtractJSONDouble(json, "tp1");
   g_currentSignal.tp2         = ExtractJSONDouble(json, "tp2");
   g_currentSignal.tp3         = ExtractJSONDouble(json, "tp3");
   g_currentSignal.confidence  = ExtractJSONDouble(json, "confidence");
   
   //--- Timeframe
   g_currentSignal.timeframe = ExtractJSONString(json, "timeframe");
   
   //--- Reason
   g_currentSignal.reason = ExtractJSONString(json, "reason");
   
   //--- Validate
   if(g_currentSignal.entry_price <= 0)
   {
      Print("[NexusOverlay] WARNING: Invalid entry price in signal");
      return false;
   }
   
   g_signalValid = true;
   
   PrintFormat("[NexusOverlay] Signal: %s @ %.2f, SL=%.2f, TP1=%.2f, TP2=%.2f, TP3=%.2f",
               g_currentSignal.signal_type, g_currentSignal.entry_price,
               g_currentSignal.stop_loss, g_currentSignal.tp1,
               g_currentSignal.tp2, g_currentSignal.tp3);
   
   return true;
}

//+------------------------------------------------------------------+
//| Extract string value from simplified JSON                          |
//+------------------------------------------------------------------+
string ExtractJSONString(string json, string key)
{
   string searchKey = "\"" + key + "\"";
   int keyPos = StringFind(json, searchKey);
   if(keyPos < 0) return "";
   
   //--- Find the colon after key
   int colonPos = StringFind(json, ":", keyPos + StringLen(searchKey));
   if(colonPos < 0) return "";
   
   //--- Find the opening quote
   int quoteStart = StringFind(json, "\"", colonPos + 1);
   if(quoteStart < 0) return "";
   
   //--- Find the closing quote
   int quoteEnd = StringFind(json, "\"", quoteStart + 1);
   if(quoteEnd < 0) return "";
   
   return StringSubstr(json, quoteStart + 1, quoteEnd - quoteStart - 1);
}

//+------------------------------------------------------------------+
//| Extract double value from simplified JSON                          |
//+------------------------------------------------------------------+
double ExtractJSONDouble(string json, string key)
{
   string searchKey = "\"" + key + "\"";
   int keyPos = StringFind(json, searchKey);
   if(keyPos < 0) return 0.0;
   
   int colonPos = StringFind(json, ":", keyPos + StringLen(searchKey));
   if(colonPos < 0) return 0.0;
   
   //--- Extract number (until comma, brace, or end)
   int start = colonPos + 1;
   while(start < StringLen(json) && StringGetCharacter(json, start) == ' ')
      start++;
   
   int end = start;
   while(end < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, end);
      if(ch == ',' || ch == '}' || ch == ']' || ch == ' ')
         break;
      end++;
   }
   
   string numStr = StringSubstr(json, start, end - start);
   return StringToDouble(numStr);
}

//+------------------------------------------------------------------+
//| Clear all overlay objects                                          |
//+------------------------------------------------------------------+
void ClearOverlayObjects()
{
   ObjectsDeleteAll(0, PREFIX_ENTRY, -1, -1);
   ObjectsDeleteAll(0, PREFIX_SL, -1, -1);
   ObjectsDeleteAll(0, PREFIX_TP1, -1, -1);
   ObjectsDeleteAll(0, PREFIX_TP2, -1, -1);
   ObjectsDeleteAll(0, PREFIX_TP3, -1, -1);
   ObjectsDeleteAll(0, PREFIX_LABEL, -1, -1);
   ObjectsDeleteAll(0, PREFIX_MARKER, -1, -1);
   ObjectsDeleteAll(0, PREFIX_ZONE, -1, -1);
   ChartRedraw();
}

//+------------------------------------------------------------------+
//| Draw complete signal overlay                                       |
//+------------------------------------------------------------------+
void DrawSignalOverlay()
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   
   //--- Draw signal label
   if(InpShowLabels)
   {
      DrawSignalLabel(digits);
   }
   
   //--- Draw entry line
   if(InpShowEntry && g_currentSignal.entry_price > 0)
   {
      DrawPriceLine(PREFIX_ENTRY + "Line", g_currentSignal.entry_price,
                    InpBuyColor, "ENTRY: " + DoubleToString(g_currentSignal.entry_price, digits), 2);
   }
   
   //--- Draw SL line
   if(InpShowSL && g_currentSignal.stop_loss > 0)
   {
      DrawPriceLine(PREFIX_SL + "Line", g_currentSignal.stop_loss,
                    InpSLColor, "SL: " + DoubleToString(g_currentSignal.stop_loss, digits), 2);
   }
   
   //--- Draw TP lines
   if(InpShowTP)
   {
      if(g_currentSignal.tp1 > 0)
         DrawPriceLine(PREFIX_TP1 + "Line", g_currentSignal.tp1,
                       InpTP1Color, "TP1: " + DoubleToString(g_currentSignal.tp1, digits), 1);
      if(g_currentSignal.tp2 > 0)
         DrawPriceLine(PREFIX_TP2 + "Line", g_currentSignal.tp2,
                       InpTP2Color, "TP2: " + DoubleToString(g_currentSignal.tp2, digits), 1);
      if(g_currentSignal.tp3 > 0)
         DrawPriceLine(PREFIX_TP3 + "Line", g_currentSignal.tp3,
                       InpTP3Color, "TP3: " + DoubleToString(g_currentSignal.tp3, digits), 1);
   }
   
   //--- Draw signal marker
   if(InpShowMarkers)
   {
      DrawSignalMarker();
   }
   
   ChartRedraw();
}

//+------------------------------------------------------------------+
//| Draw signal label on chart                                         |
//+------------------------------------------------------------------+
void DrawSignalLabel(int digits)
{
   string name = PREFIX_LABEL + "Main";
   string text = "";
   color labelColor = InpWaitColor;
   
   if(g_currentSignal.signal_type == "BUY")
   {
      text = "▲ BUY";
      labelColor = InpBuyColor;
   }
   else if(g_currentSignal.signal_type == "SELL")
   {
      text = "▼ SELL";
      labelColor = InpSellColor;
   }
   else
   {
      text = "● WAIT";
      labelColor = InpWaitColor;
   }
   
   //--- Add confidence if available
   if(g_currentSignal.confidence > 0)
      text += StringFormat(" (%.0f%%)", g_currentSignal.confidence * 100);
   
   //--- Add timeframe
   if(g_currentSignal.timeframe != "")
      text += " [" + g_currentSignal.timeframe + "]";
   
   //--- Add reason if available
   if(g_currentSignal.reason != "")
      text += "\n" + g_currentSignal.reason;
   
   //--- Create label object
   ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 20);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 50);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_RIGHT_UPPER);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpFontSize + 4);
   ObjectSetInteger(0, name, OBJPROP_COLOR, labelColor);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   
   //--- Create background box
   string bgName = PREFIX_LABEL + "BG";
   ObjectCreate(0, bgName, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, bgName, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
   ObjectSetInteger(0, bgName, OBJPROP_XDISTANCE, 15);
   ObjectSetInteger(0, bgName, OBJPROP_YDISTANCE, 45);
   ObjectSetInteger(0, bgName, OBJPROP_XSIZE, 220);
   ObjectSetInteger(0, bgName, OBJPROP_YSIZE, 80);
   ObjectSetInteger(0, bgName, OBJPROP_BGCOLOR, C'20,20,30');
   ObjectSetInteger(0, bgName, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, bgName, OBJPROP_COLOR, labelColor);
   ObjectSetInteger(0, bgName, OBJPROP_BACK, false);
   ObjectSetInteger(0, bgName, OBJPROP_SELECTABLE, false);
}

//+------------------------------------------------------------------+
//| Draw a horizontal price line                                       |
//+------------------------------------------------------------------+
void DrawPriceLine(string name, double price, color lineColor, string label, int width)
{
   //--- Remove existing
   ObjectDelete(0, name);
   
   datetime timeStart = iTime(_Symbol, PERIOD_CURRENT, 50);
   datetime timeEnd   = iTime(_Symbol, PERIOD_CURRENT, 0) + PeriodSeconds(PERIOD_CURRENT) * 30;
   
   if(timeStart == 0) timeStart = TimeCurrent() - 3600;
   if(timeEnd == 0)   timeEnd   = TimeCurrent() + 1800;
   
   ObjectCreate(0, name, OBJ_TREND, 0, timeStart, price, timeEnd, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, lineColor);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
   ObjectSetInteger(0, name, OBJPROP_STYLE, InpLineStyle);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   
   //--- Add price label at right edge
   string labelName = name + "_label";
   ObjectCreate(0, labelName, OBJ_TEXT, 0, timeEnd, price);
   ObjectSetString(0, labelName, OBJPROP_TEXT, " " + label);
   ObjectSetString(0, labelName, OBJPROP_FONT, "Arial");
   ObjectSetInteger(0, labelName, OBJPROP_FONTSIZE, InpFontSize);
   ObjectSetInteger(0, labelName, OBJPROP_COLOR, lineColor);
   ObjectSetInteger(0, labelName, OBJPROP_ANCHOR, ANCHOR_LEFT);
   ObjectSetInteger(0, labelName, OBJPROP_SELECTABLE, false);
}

//+------------------------------------------------------------------+
//| Draw signal marker (arrow on chart)                                |
//+------------------------------------------------------------------+
void DrawSignalMarker()
{
   string name = PREFIX_MARKER + "Arrow";
   ObjectDelete(0, name);
   
   datetime markerTime = iTime(_Symbol, PERIOD_CURRENT, 0);
   double markerPrice = g_currentSignal.entry_price;
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   
   ENUM_OBJECT arrowType = OBJ_ARROW_RIGHT_PRICE;
   color arrowColor = InpWaitColor;
   
   if(g_currentSignal.signal_type == "BUY")
   {
      arrowType = OBJ_ARROW_UP;
      arrowColor = InpBuyColor;
      //--- Place below candle
      double low = iLow(_Symbol, PERIOD_CURRENT, 0);
      markerPrice = low - (5 * _Point * MathPow(10, digits > 2 ? digits - 2 : 0));
   }
   else if(g_currentSignal.signal_type == "SELL")
   {
      arrowType = OBJ_ARROW_DOWN;
      arrowColor = InpSellColor;
      //--- Place above candle
      double high = iHigh(_Symbol, PERIOD_CURRENT, 0);
      markerPrice = high + (5 * _Point * MathPow(10, digits > 2 ? digits - 2 : 0));
   }
   
   ObjectCreate(0, name, arrowType, 0, markerTime, markerPrice);
   ObjectSetInteger(0, name, OBJPROP_COLOR, arrowColor);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 3);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
}

//+------------------------------------------------------------------+
//| Update price line positions (for dynamic movement)                 |
//+------------------------------------------------------------------+
void UpdatePriceLinePositions()
{
   //--- Extend lines to current time
   datetime now = TimeCurrent();
   datetime timeEnd = now + PeriodSeconds(PERIOD_CURRENT) * 30;
   
   string lineNames[] = {PREFIX_ENTRY + "Line", PREFIX_SL + "Line",
                          PREFIX_TP1 + "Line", PREFIX_TP2 + "Line", PREFIX_TP3 + "Line"};
   
   for(int i = 0; i < ArraySize(lineNames); i++)
   {
      if(ObjectFind(0, lineNames[i]) >= 0)
      {
         datetime time2 = (datetime)ObjectGetInteger(0, lineNames[i], OBJPROP_TIME, 1);
         if(time2 < timeEnd)
         {
            ObjectSetInteger(0, lineNames[i], OBJPROP_TIME, 1, timeEnd);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Chart event handler                                                |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   //--- Reserved for interactive features
}
//+------------------------------------------------------------------+
