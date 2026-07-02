;; VLUT ADE plugin: gm/ID sweep sizing driven from inside Virtuoso.
;;
;;   load("/path/to/VLUT/virtuoso/vlut_ade.il")
;;
;; Adds a "VLUT" menu to the CIW (or call VLUT()). Workflow:
;;   1. point the form at an ADE netlist dir (input.scs), set design
;;      variables, fixed gm/ID targets and one swept gm/ID device group
;;   2. Run sweep: for every sweep value VLUT resizes the netlist
;;      (op -> LUT -> op iteration, W split into m units) and runs the
;;      netlist's own ADE analyses with Spectre
;;   3. the metric (any ADE/OCEAN calculator formula) is evaluated on
;;      every result: table + best point in the form, metric-vs-gm/ID
;;      plot in ViVA, best-point waveform plot, and one-click push of
;;      the best sizes back to the schematics.

VLUTRoot = simplifyFilename(strcat(get_filename(piport) "/../.."))
unless(isDir(strcat(VLUTRoot "/venv"))
  VLUTRoot = getShellEnvVar("VLUT_ROOT") || VLUTRoot)
VLUTCli = strcat(VLUTRoot "/venv/bin/vlut-cli")
VLUTState = nil   ; assoc-free list: (outdir analysis metric goal best xs ys)
VLUTScanDevs = nil    ; device names from the scanned netlist
VLUTScanNets = nil    ; top-level net names from the scanned netlist
VLUTWaveExpr = "v(\"out\")"

;; metric templates: (label formula-with-%s-for-net) -- no typing needed
VLUTMetricTypes = list(
  list("DC gain [dB]"         "ymax(db20(v(\"%s\")))")
  list("Unity-gain freq [Hz]" "cross(db20(v(\"%s\")) 0 1 \"falling\")")
  list("Phase margin [deg]"   "phaseMargin(v(\"%s\"))")
  list("Gain-BW product"      "gainBwProd(v(\"%s\"))")
  list("Bandwidth -3dB [Hz]"  "bandwidth(v(\"%s\") 3 \"low\")")
  list("Peak-to-peak"         "peakToPeak(v(\"%s\"))")
  list("Max value"            "ymax(v(\"%s\"))")
  list("Min value"            "ymin(v(\"%s\"))"))

VLUTWaveTypes = list(
  list("Magnitude [dB]" "db20(v(\"%s\"))")
  list("Phase [deg]"    "phase(v(\"%s\"))")
  list("Voltage"        "v(\"%s\")"))

procedure(VLUTLabels(templates) foreach(mapcar e templates car(e)))
procedure(VLUTCompose(templates label net)
  let((e) e = car(exists(x templates car(x) == label))
    if(e then sprintf(nil cadr(e) net) else sprintf(nil "v(\"%s\")" net))))
procedure(VLUTChomp(s)
  when(s while(rexMatchp("[ \t\n\r]$" s) s = substring(s 1 sub1(length(s)))))
  s)

;; ---------------------------------------------------------------- helpers
procedure(VLUTTokens(s) parseString(s " \t"))

procedure(VLUTJstr(s) sprintf(nil "\"%s\"" s))

procedure(VLUTParseFixedLine(line)
  ;; "M3 M4 : 10 L=0.7" -> list(devices gmidStr lumStr|nil)
  let((toks devs gmid lum sep)
    toks = VLUTTokens(line)
    foreach(tok toks
      cond(
        (tok == ":" sep = t)
        (!sep devs = cons(tok devs))
        (pcreMatchp("^[Ll]=" tok) lum = cadr(parseString(tok "=")))
        (t unless(gmid gmid = tok))))
    if(devs && gmid then list(reverse(devs) gmid lum) else nil)))

procedure(VLUTDevsJson(devs)
  buildString(foreach(mapcar d devs VLUTJstr(d)) ","))

procedure(VLUTReadResults(outdir)
  let((p pts)
    p = errset(infile(strcat(outdir "/results.il")))
    when(car(p)
      pts = car(lineread(car(p)))   ; file is one line: ((idx gmid conv psf)...)
      close(car(p)))
    pts))

procedure(VLUTPdkInventory()
  ;; ((name title (corners...) ((dev pol (lutcorners...)) ...)) ...)
  let((tmp p inv)
    tmp = strcat(getShellEnvVar("HOME") "/.cache/vlut_pdks.il")
    sh(sprintf(nil "%s pdks > %s 2>/dev/null" VLUTCli tmp))
    p = errset(infile(tmp))
    when(car(p)
      inv = car(lineread(car(p)))
      close(car(p)))
    inv))

procedure(VLUTPdkNames(inv)
  foreach(mapcar e inv car(e)))

procedure(VLUTPdkEntry(inv name)
  car(exists(e inv car(e) == name)))

;; ---------------------------------------------------------------- job run
procedure(VLUTWriteJob(form outdir)
  let((p fixed params sweepl)
    p = outfile(strcat(outdir "/job.json"))
    fprintf(p "{\n")
    fprintf(p " \"netlist_dir\": %s,\n" VLUTJstr(form->ndir->value))
    fprintf(p " \"pdk\": %s,\n" VLUTJstr(form->pdksel->value))
    fprintf(p " \"corner\": %s,\n" VLUTJstr(form->corner->value))
    fprintf(p " \"w_max\": %ge-6,\n" form->wmax->value)
    fprintf(p " \"max_iter\": %d,\n" form->maxiter->value)
    fprintf(p " \"outdir\": %s,\n" VLUTJstr(outdir))
    params = foreach(mapcar tok VLUTTokens(form->params->value)
      let((kv) kv = parseString(tok "=")
        sprintf(nil "%s: %s" VLUTJstr(car(kv)) VLUTJstr(cadr(kv)))))
    fprintf(p " \"parameters\": {%s},\n" buildString(params ","))
    fixed = nil
    foreach(line parseString(form->fixed->value "\n")
      let((f) f = VLUTParseFixedLine(line)
        when(f
          fixed = cons(sprintf(nil "{\"devices\": [%s], \"gmid\": %s%s}"
            VLUTDevsJson(car(f)) cadr(f)
            if(caddr(f) then sprintf(nil ", \"l\": %se-6" caddr(f)) else ""))
            fixed))))
    fprintf(p " \"fixed\": [%s],\n" buildString(reverse(fixed) ","))
    sweepl = form->sweepl->value    ;; float field: 0 = keep current L
    ;; sweepdevs is a listbox -> value is already a list of device names
    fprintf(p " \"sweep\": {\"devices\": [%s], \"gmid\": [%s]%s}\n"
      VLUTDevsJson(form->sweepdevs->value)
      buildString(VLUTTokens(form->sweepvals->value) ",")
      if(numberp(sweepl) && sweepl > 0.0
         then sprintf(nil ", \"l\": %ge-6" sweepl) else ""))
    fprintf(p "}\n")
    close(p)))

procedure(VLUTRun(form)
  let((outdir ts metric net)
    net = form->metricnet->value
    metric = VLUTCompose(VLUTMetricTypes form->metrictype->value net)
    VLUTWaveExpr = VLUTCompose(VLUTWaveTypes form->wavetype->value net)
    ts = buildString(parseString(getCurrentTime() " :") "_")
    outdir = sprintf(nil "%s/vlut_runs/sweep_%s" getShellEnvVar("HOME") ts)
    createDirHier(outdir)
    VLUTWriteJob(form outdir)
    VLUTState = list(outdir form->analysis->value metric
                     form->goal->value nil nil nil)
    form->report->value = sprintf(nil "running... metric=%s\nprogress in CIW"
                                  metric)
    printf("VLUT: sweep started (metric=%s) -> %s\n" metric outdir)
    ipcBeginProcess(sprintf(nil "%s run %s/job.json" VLUTCli outdir)
                    "" 'VLUTIpcData 'VLUTIpcData 'VLUTIpcDone)))

procedure(VLUTIpcData(_cid data) printf("VLUT| %s" data))

procedure(VLUTIpcDone(_cid _status)
  printf("VLUT: sweep finished, evaluating metric...\n")
  VLUTEvalResults())

;; ---------------------------------------------------------------- results
procedure(VLUTSelectAnalysis(aname)
  let((sym)
    sym = car(exists(r results() sprintf(nil "%L" r) == aname))
    unless(sym
      sym = car(exists(r results() pcreMatchp(aname sprintf(nil "%L" r)))))
    when(sym selectResult(sym))
    sym))

procedure(VLUTEvalResults()
  let((outdir aname metric goal pts rows best bestval val txt xs ys idx gmid conv psf)
    outdir = nth(0 VLUTState)  aname = nth(1 VLUTState)
    metric = nth(2 VLUTState)  goal  = nth(3 VLUTState)
    pts = VLUTReadResults(outdir)
    if(!pts then printf("VLUT: no results in %s\n" outdir)
    else
      foreach(pt pts
        idx = nth(0 pt)  gmid = nth(1 pt)
        conv = nth(2 pt) psf  = nth(3 pt)
        val = nil
        when(car(errset(openResults(psf)))
          when(VLUTSelectAnalysis(aname)
            val = car(errset(evalstring(metric)))))
        unless(numberp(val) val = nil)
        when(val
          xs = cons(float(gmid) xs)
          ys = cons(float(val) ys)
          when(!best || if(goal == "maximize" then val > bestval
                                              else val < bestval)
            best = idx  bestval = val))
        rows = cons(list(idx gmid conv val) rows))
      rows = reverse(rows)
      txt = sprintf(nil "%-5s %-8s %-6s %-16s\n" "pt" "gm/ID" "conv" "metric")
      foreach(r rows
        txt = strcat(txt sprintf(nil "%-5s %-8s %-6s %-16s%s\n"
          sprintf(nil "%L" nth(0 r)) sprintf(nil "%L" nth(1 r))
          if(nth(2 r) then "yes" else "NO")
          sprintf(nil "%L" nth(3 r))
          if(nth(0 r) == best then "  <== BEST" else ""))))
      txt = strcat(txt sprintf(nil "\nbest: pt%L  metric=%L (%s)\n"
                               best bestval goal))
      VLUTState = list(outdir aname metric goal best reverse(xs) reverse(ys))
      when(boundp('VLUTForm) && hiIsForm(VLUTForm)
        VLUTForm->report->value = txt)
      printf("%s" txt))))

procedure(VLUTPlotMetric()
  let((metric xs ys win wave)
    metric = nth(2 VLUTState)
    xs = nth(5 VLUTState)  ys = nth(6 VLUTState)
    if(length(xs) < 2 then printf("VLUT: nothing to plot\n")
    else
      wave = drCreateWaveform(drCreateVec('double xs) drCreateVec('double ys))
      win = awvCreatePlotWindow()
      awvPlotWaveform(win wave)
      errset(awvSetXAxisLabel(win "gm/ID target"))
      errset(awvSetYAxisLabel(win metric)))))

procedure(VLUTPlotBestWave(form)
  let((outdir aname best pts psf expr win)
    outdir = nth(0 VLUTState)  aname = nth(1 VLUTState)
    best = nth(4 VLUTState)
    expr = VLUTWaveExpr
    if(!best && best != 0 then printf("VLUT: run a sweep first\n")
    else
      pts = VLUTReadResults(outdir)
      psf = nth(3 nth(best pts))
      openResults(psf)
      VLUTSelectAnalysis(aname)
      win = awvCreatePlotWindow()
      awvSetCurrentWindow(win)
      plot(evalstring(expr) ?expr list(expr)))))

procedure(VLUTApplyBest()
  let((outdir best out)
    outdir = nth(0 VLUTState)  best = nth(4 VLUTState)
    if(!best && best != 0 then printf("VLUT: run a sweep first\n")
    else
      out = strcat(outdir "/apply_best.il")
      sh(sprintf(nil "%s apply %s/results.json %d %s"
                 VLUTCli outdir best out))
      if(isFile(out) then
        load(out)
        printf("VLUT: applied pt%d sizes to schematics\n" best)
      else printf("VLUT: apply failed (see shell output)\n")))))

;; ---------------------------------------------------------------- form/UI
;; The form has no free-text device/dir/formula entry: netlist dir comes
;; from a file browser, corner/PDK/device/net/metric from dropdowns and
;; listboxes.  Only numbers and design-variable parameters are typed.

procedure(VLUTPdkCorners(pdkname)
  let((e) e = VLUTPdkEntry(VLUTPdkInventory() pdkname)
    if(e then caddr(e) else list("tt"))))

procedure(VLUTGet(saved sym dflt)
  let((c) c = assoc(sym saved) if(c then cadr(c) else dflt)))

;; keep a restored value valid against the current choices, so rebuilding
;; a form after a re-scan / PDK change never fails with
;; "value must be contained within the list of choices"
procedure(VLUTOneOf(saved sym choices)
  let((v) v = VLUTGet(saved sym nil)
    if(v && member(v choices) then v else car(choices))))
procedure(VLUTSubsetOf(saved sym choices)
  setof(x VLUTGet(saved sym nil) member(x choices)))

procedure(VLUTSaveVals(form)
  ;; snapshot current field values so a rebuild can restore them
  list(
    list('ndir       form->ndir->value)
    list('pdksel     form->pdksel->value)
    list('corner     form->corner->value)
    list('wmax       form->wmax->value)
    list('maxiter    form->maxiter->value)
    list('params     form->params->value)
    list('sweepdevs  form->sweepdevs->value)
    list('sweepvals  form->sweepvals->value)
    list('sweepl     form->sweepl->value)
    list('fixed      form->fixed->value)
    list('analysis   form->analysis->value)
    list('metrictype form->metrictype->value)
    list('metricnet  form->metricnet->value)
    list('goal       form->goal->value)
    list('wavetype   form->wavetype->value)
    list('report     form->report->value)))

;; browse for the ADE netlist directory with a native file chooser
procedure(VLUTBrowseDir(form)
  let((tmp p s)
    tmp = sprintf(nil "%s/.cache/vlut_pick.txt" getShellEnvVar("HOME"))
    sh(strcat("zenity --file-selection --directory "
              "--title='Select ADE netlist dir (has input.scs)' > " tmp
              " 2>/dev/null"))
    p = errset(infile(tmp))
    when(car(p)
      s = gets(nil car(p)) close(car(p))
      s = VLUTChomp(s)
      when(s && s != "" form->ndir->value = s
        VLUTScanNetlist(form)))))

;; one-click: netlist the current open ADE/Maestro session, import it here
procedure(VLUTFromADE(form)
  let((s dir)
    s = car(errset(asiGetCurrentSession()))
    if(!s then
      hiDisplayAppDBox(?name 'VLUTNoAde ?dboxBanner "VLUT"
        ?dboxText "No open ADE Explorer / Assembler session found."
        ?dialogType hicWarningDialog ?buttonList list("OK"))
    else
      printf("VLUT: netlisting current ADE session...\n")
      errset(asiNetlist(s))
      dir = car(errset(asiGetNetlistDir(s)))
      if(dir && isDir(dir) then
        form->ndir->value = dir
        printf("VLUT: imported ADE netlist %s\n" dir)
        VLUTScanNetlist(form)
      else
        hiDisplayAppDBox(?name 'VLUTNoDir ?dboxBanner "VLUT"
          ?dboxText "Netlist directory not found; run the ADE netlister once."
          ?dialogType hicWarningDialog ?buttonList list("OK"))))))

;; open the form and immediately pull the current ADE netlist
procedure(VLUTOpenFromADE()
  VLUT()
  VLUTFromADE(VLUTForm))

;; scan the netlist for device + net names, then rebuild with them filled
procedure(VLUTScanNetlist(form)
  let((dir out p line)
    dir = form->ndir->value
    if(dir == "" then printf("VLUT: pick a netlist dir first\n")
    else
      out = sprintf(nil "%s/.cache/vlut_scan.il" getShellEnvVar("HOME"))
      sh(sprintf(nil "%s scan-il %s %s > %s 2>/dev/null"
                 VLUTCli dir form->pdksel->value out))
      p = errset(infile(out))
      if(car(p) then
        line = car(lineread(car(p))) close(car(p))
        VLUTScanDevs = nth(0 line)
        VLUTScanNets = nth(1 line)
        printf("VLUT: scanned %d devices, %d nets\n"
               length(VLUTScanDevs) length(VLUTScanNets))
        VLUTBuildForm(VLUTSaveVals(form))
      else printf("VLUT: scan failed for %s\n" dir)))))

procedure(VLUTAddFixed(form)
  ;; append the selected fixed-device group to the read-only summary
  let((devs g txt)
    devs = form->fixdevs->value
    if(!devs then printf("VLUT: select devices for the fixed group\n")
    else
      g = sprintf(nil "%s : %g%s"
            buildString(devs " ") form->fixgmid->value
            if(form->fixl->value > 0.0
               then sprintf(nil " L=%g" form->fixl->value) else ""))
      txt = form->fixed->value
      form->fixed->value = if(txt == "" then g else strcat(txt "\n" g)))))

procedure(VLUTClearFixed(form) form->fixed->value = "")

procedure(VLUTBuildForm(saved)
  let((names corners devs nets mlabels wlabels)
    names = VLUTPdkNames(VLUTPdkInventory()) || list("default")
    corners = VLUTPdkCorners(VLUTGet(saved 'pdksel car(names)))
    ;; before a scan the lists are empty; a lone placeholder must never be
    ;; carried into a rebuild as a selected value (VLUTSubsetOf/OneOf guard it)
    devs = VLUTScanDevs || list("<scan a netlist first>")
    nets = VLUTScanNets || list("<scan a netlist first>")
    mlabels = VLUTLabels(VLUTMetricTypes)
    wlabels = VLUTLabels(VLUTWaveTypes)
    when(boundp('VLUTForm) && hiIsForm(VLUTForm) hiDeleteForm(VLUTForm))
    hiCreateAppForm(
      ?name 'VLUTForm
      ?formTitle "VLUT gm/ID Sweep Sizing"
      ?buttonLayout 'Close
      ?fields list(
        hiCreateStringField(?name 'ndir ?prompt "ADE netlist dir" ?editable nil
          ?value VLUTGet(saved 'ndir ""))
        hiCreateButton(?name 'adebtn
          ?buttonText "Netlist open ADE/Maestro -> import"
          ?callback "VLUTFromADE(VLUTForm)")
        hiCreateButton(?name 'browsebtn ?buttonText "...or Browse netlist dir"
          ?callback "VLUTBrowseDir(VLUTForm)")
        hiCreateButton(?name 'scanbtn ?buttonText "Re-scan devices/nets"
          ?callback "VLUTScanNetlist(VLUTForm)")
        hiCreateCyclicField(?name 'pdksel ?prompt "PDK" ?choices names
          ?value VLUTOneOf(saved 'pdksel names)
          ?callback "VLUTBuildForm(VLUTSaveVals(VLUTForm))")
        hiCreateCyclicField(?name 'corner ?prompt "Corner" ?choices corners
          ?value VLUTOneOf(saved 'corner corners))
        hiCreateFloatField(?name 'wmax ?prompt "Max unit W [um]"
          ?value VLUTGet(saved 'wmax 10.0))
        hiCreateIntField(?name 'maxiter ?prompt "Max iterations"
          ?value VLUTGet(saved 'maxiter 8))
        hiCreateStringField(?name 'params
          ?prompt "Design variables (A=1 CL=2p)"
          ?value VLUTGet(saved 'params ""))
        ;; ---- sweep group (device listbox + numeric values) ----
        hiCreateListBoxField(?name 'sweepdevs ?prompt "Sweep devices"
          ?choices devs ?multipleSelect t
          ?value VLUTSubsetOf(saved 'sweepdevs devs))
        hiCreateStringField(?name 'sweepvals ?prompt "Sweep gm/ID values"
          ?value VLUTGet(saved 'sweepvals "8 12 16 20"))
        hiCreateFloatField(?name 'sweepl ?prompt "Sweep L [um] (0=keep)"
          ?value VLUTGet(saved 'sweepl 0.0))
        ;; ---- fixed-group builder ----
        hiCreateListBoxField(?name 'fixdevs ?prompt "Fixed devices"
          ?choices devs ?multipleSelect t)
        hiCreateFloatField(?name 'fixgmid ?prompt "Fixed gm/ID" ?value 10.0)
        hiCreateFloatField(?name 'fixl ?prompt "Fixed L [um] (0=keep)"
          ?value 0.0)
        hiCreateButton(?name 'addfixbtn ?buttonText "Add fixed group"
          ?callback "VLUTAddFixed(VLUTForm)")
        hiCreateButton(?name 'clrfixbtn ?buttonText "Clear"
          ?callback "VLUTClearFixed(VLUTForm)")
        hiCreateMLTextField(?name 'fixed ?prompt "Fixed groups" ?editable nil
          ?value VLUTGet(saved 'fixed ""))
        ;; ---- analysis + metric (dropdown + net dropdown) ----
        hiCreateCyclicField(?name 'analysis ?prompt "Analysis"
          ?choices list("ac" "tran" "dc")
          ?value VLUTGet(saved 'analysis "ac"))
        hiCreateCyclicField(?name 'metrictype ?prompt "Metric"
          ?choices mlabels ?value VLUTOneOf(saved 'metrictype mlabels))
        hiCreateCyclicField(?name 'metricnet ?prompt "on net"
          ?choices nets ?value VLUTOneOf(saved 'metricnet nets))
        hiCreateCyclicField(?name 'goal ?prompt "Goal"
          ?choices list("maximize" "minimize")
          ?value VLUTOneOf(saved 'goal list("maximize" "minimize")))
        hiCreateCyclicField(?name 'wavetype ?prompt "Waveform"
          ?choices wlabels ?value VLUTOneOf(saved 'wavetype wlabels))
        ;; ---- actions ----
        hiCreateButton(?name 'runbtn ?buttonText "Run sweep"
          ?callback "VLUTRun(VLUTForm)")
        hiCreateButton(?name 'plotbtn ?buttonText "Plot metric vs gm/ID"
          ?callback "VLUTPlotMetric()")
        hiCreateButton(?name 'wavebtn ?buttonText "Plot best waveform"
          ?callback "VLUTPlotBestWave(VLUTForm)")
        hiCreateButton(?name 'applybtn ?buttonText "Apply best to schematic"
          ?callback "VLUTApplyBest()")
        hiCreateButton(?name 'mgrbtn ?buttonText "PDK / LUT Manager..."
          ?callback "VLUTMgr()")
        hiCreateMLTextField(?name 'report ?prompt "Results" ?editable nil
          ?value VLUTGet(saved 'report ""))))
    hiDisplayForm(VLUTForm)
    t))

procedure(VLUT() VLUTBuildForm(nil))

;; ------------------------------------------------- PDK / LUT manager form
procedure(VLUTMgrStatusText(inv pdkname)
  let((e txt)
    e = VLUTPdkEntry(inv pdkname)
    if(!e then "no PDK descriptors found (add pdks/<name>.yaml)"
    else
      txt = sprintf(nil "PDK: %s   corners: %s\n\n%-10s %-4s %s\n"
              cadr(e) buildString(caddr(e) " ")
              "device" "pol" "LUT corners done")
      foreach(d cadddr(e)
        txt = strcat(txt sprintf(nil "%-10s %-4s %s\n"
          car(d) cadr(d)
          if(caddr(d) then buildString(caddr(d) " ") else "(none)"))))
      txt)))

procedure(VLUTMgrRefresh()
  let((inv)
    inv = VLUTPdkInventory()
    when(boundp('VLUTMgrForm) && hiIsForm(VLUTMgrForm)
      VLUTMgrForm->lutstatus->value =
        VLUTMgrStatusText(inv VLUTMgrForm->mpdk->value))))

procedure(VLUTMgrCharDone(_cid _status)
  printf("VLUT: characterization finished\n")
  VLUTMgrRefresh())

procedure(VLUTMgrChar(form)
  let((devs)
    devs = buildString(VLUTTokens(form->chardevs->value) " ")
    if(devs == "" then printf("VLUT: no devices given\n")
    else
      printf("VLUT: characterizing %s @ %s (progress below)\n"
             devs form->charcorner->value)
      ipcBeginProcess(
        sprintf(nil "%s char %s %s %g %d %s"
          VLUTCli form->mpdk->value form->charcorner->value
          form->chartemp->value form->charnproc->value devs)
        "" 'VLUTIpcData 'VLUTIpcData 'VLUTMgrCharDone))))

procedure(VLUTMgrPdkChanged(field _scope)
  ;; refresh status + prefill device list when the PDK cyclic changes
  let((inv e)
    inv = VLUTPdkInventory()
    e = VLUTPdkEntry(inv field->value)
    when(boundp('VLUTMgrForm) && hiIsForm(VLUTMgrForm)
      VLUTMgrForm->lutstatus->value = VLUTMgrStatusText(inv field->value)
      when(e
        VLUTMgrForm->chardevs->value =
          buildString(foreach(mapcar d cadddr(e) car(d)) " ")
        VLUTMgrForm->charcorner->value = car(caddr(e))))))

procedure(VLUTMgr()
  let((inv names e)
    inv = VLUTPdkInventory()
    names = VLUTPdkNames(inv) || list("default")
    e = VLUTPdkEntry(inv car(names))
    unless(boundp('VLUTMgrForm) && hiIsForm(VLUTMgrForm)
      hiCreateAppForm(
        ?name 'VLUTMgrForm
        ?formTitle "VLUT PDK / LUT Manager"
        ?buttonLayout 'Close
        ?fields list(
          hiCreateCyclicField(?name 'mpdk ?prompt "PDK" ?choices names
            ?value car(names) ?callback "VLUTMgrPdkChanged")
          hiCreateMLTextField(?name 'lutstatus ?prompt "LUT status"
            ?defValue VLUTMgrStatusText(inv car(names)))
          hiCreateStringField(?name 'chardevs ?prompt "Devices to characterize"
            ?defValue if(e then
              buildString(foreach(mapcar d cadddr(e) car(d)) " ") else ""))
          hiCreateStringField(?name 'charcorner ?prompt "Corner"
            ?defValue if(e then car(caddr(e)) else "tt"))
          hiCreateFloatField(?name 'chartemp ?prompt "Temp [C]"
            ?defValue 27.0)
          hiCreateIntField(?name 'charnproc ?prompt "Parallel Spectre jobs"
            ?defValue 6)
          hiCreateButton(?name 'charbtn ?buttonText "Characterize LUTs"
            ?callback "VLUTMgrChar(VLUTMgrForm)")
          hiCreateButton(?name 'refreshbtn ?buttonText "Refresh status"
            ?callback "VLUTMgrRefresh()")
          hiCreateLabel(?name 'nlab ?labelText
            "New PDK: cp pdks/example.yaml.template pdks/<name>.yaml, edit, Refresh"))))
    hiDisplayForm(VLUTMgrForm)
    t))

;; ---------------------------------------------------------------- menus
;; build the VLUT pulldown (same items everywhere)
procedure(VLUTMenuItems()
  list(hiCreateMenuItem(?name 'vlutFromAde
         ?itemText "Netlist current ADE/Maestro into VLUT..."
         ?callback "VLUTOpenFromADE()")
       hiCreateMenuItem(?name 'vlutOpen
         ?itemText "gm/ID Sweep Sizing..."
         ?callback "VLUT()")
       hiCreateMenuItem(?name 'vlutMgrItem
         ?itemText "PDK / LUT Manager..."
         ?callback "VLUTMgr()")))

;; add/refresh the VLUT banner menu on any window (idempotent by name)
procedure(VLUTAddMenuTo(win)
  let((idx i)
    i = 0
    foreach(m hiGetBannerMenus(win)
      when(!idx && pcreMatchp("^VLUTMenu" sprintf(nil "%L" m)) idx = i)
      i = i + 1)
    when(idx errset(hiDeleteBannerMenu(win idx)))
    errset(hiInsertBannerMenu(win
      hiCreatePulldownMenu(gensym('VLUTMenu) "VLUT" VLUTMenuItems())
      length(hiGetBannerMenus(win))))))

;; put the menu on every open ADE Explorer / Assembler (Maestro) window
procedure(VLUTAddMenuToAllAde()
  foreach(w hiGetWindowList()
    when(member(car(errset(hiGetAppType(w)))
               list("explorer" "assembler" "adexl"))
      VLUTAddMenuTo(w))))

;; fires when a maestro/adexl window opens -> menu appears inside it
procedure(VLUTAdeTrigger(@rest _args) VLUTAddMenuToAllAde())

foreach(vt list("maestro" "adexl")
  errset(deRegUserTriggers(vt 'VLUTAdeTrigger)))

;; CIW menu + any already-open Maestro windows (so no reopen needed now)
VLUTAddMenuTo(hiGetCIWindow())
VLUTAddMenuToAllAde()

printf("VLUT loaded. Menu 'VLUT' is in the CIW and in ADE Explorer/Assembler%s"
       " windows (root: %s)\n" "" VLUTRoot)
