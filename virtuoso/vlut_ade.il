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

;; ---------------------------------------------------------------- job run
procedure(VLUTWriteJob(form outdir)
  let((p fixed params sweepl)
    p = outfile(strcat(outdir "/job.json"))
    fprintf(p "{\n")
    fprintf(p " \"netlist_dir\": %s,\n" VLUTJstr(form->ndir->value))
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
    sweepl = form->sweepl->value
    fprintf(p " \"sweep\": {\"devices\": [%s], \"gmid\": [%s]%s}\n"
      VLUTDevsJson(VLUTTokens(form->sweepdevs->value))
      buildString(VLUTTokens(form->sweepvals->value) ",")
      if(sweepl != "" then sprintf(nil ", \"l\": %se-6" sweepl) else ""))
    fprintf(p "}\n")
    close(p)))

procedure(VLUTRun(form)
  let((outdir ts)
    ts = buildString(parseString(getCurrentTime() " :") "_")
    outdir = sprintf(nil "%s/vlut_runs/sweep_%s" getShellEnvVar("HOME") ts)
    createDirHier(outdir)
    VLUTWriteJob(form outdir)
    VLUTState = list(outdir form->analysis->value form->metric->value
                     form->goal->value nil nil nil)
    form->report->value = "running... progress in CIW"
    printf("VLUT: sweep started -> %s\n" outdir)
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
    expr = form->waveexpr->value
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
procedure(VLUT()
  unless(boundp('VLUTForm) && hiIsForm(VLUTForm)
    hiCreateAppForm(
      ?name 'VLUTForm
      ?formTitle "VLUT gm/ID Sweep Sizing"
      ?buttonLayout 'Close
      ?fields list(
        hiCreateStringField(?name 'ndir ?prompt "ADE netlist dir" ?defValue "")
        hiCreateStringField(?name 'corner ?prompt "Corner" ?defValue "tt")
        hiCreateFloatField(?name 'wmax ?prompt "Max unit W [um]" ?defValue 10.0)
        hiCreateIntField(?name 'maxiter ?prompt "Max iterations" ?defValue 8)
        hiCreateStringField(?name 'params
          ?prompt "Design variables (A=1 CL=2p)" ?defValue "")
        hiCreateMLTextField(?name 'fixed
          ?prompt "Fixed targets (per line: M3 M4 : 10 L=0.7)" ?defValue "")
        hiCreateStringField(?name 'sweepdevs ?prompt "Sweep devices"
          ?defValue "M1 M2")
        hiCreateStringField(?name 'sweepvals ?prompt "Sweep gm/ID values"
          ?defValue "8 12 16 20")
        hiCreateStringField(?name 'sweepl
          ?prompt "Sweep devices L [um] (opt)" ?defValue "")
        hiCreateCyclicField(?name 'analysis ?prompt "Analysis"
          ?choices list("ac" "tran" "dc") ?value "ac")
        hiCreateStringField(?name 'metric ?prompt "Metric (ADE formula)"
          ?defValue "gainBwProd(v(\"out\"))")
        hiCreateCyclicField(?name 'goal ?prompt "Goal"
          ?choices list("maximize" "minimize") ?value "maximize")
        hiCreateStringField(?name 'waveexpr ?prompt "Waveform expr (plot)"
          ?defValue "db20(v(\"out\"))")
        hiCreateButton(?name 'runbtn ?buttonText "Run sweep"
          ?callback "VLUTRun(VLUTForm)")
        hiCreateButton(?name 'plotbtn ?buttonText "Plot metric vs gm/ID"
          ?callback "VLUTPlotMetric()")
        hiCreateButton(?name 'wavebtn ?buttonText "Plot best waveform"
          ?callback "VLUTPlotBestWave(VLUTForm)")
        hiCreateButton(?name 'applybtn ?buttonText "Apply best to schematic"
          ?callback "VLUTApplyBest()")
        hiCreateMLTextField(?name 'report ?prompt "Results" ?defValue ""))))
  hiDisplayForm(VLUTForm)
  t)

;; CIW menu (once)
unless(member('VLUTMenu hiGetBannerMenus(hiGetCIWindow()))
  hiInsertBannerMenu(hiGetCIWindow()
    hiCreatePulldownMenu('VLUTMenu "VLUT"
      list(hiCreateMenuItem(?name 'vlutOpen
             ?itemText "gm/ID Sweep Sizing..."
             ?callback "VLUT()")))
    length(hiGetBannerMenus(hiGetCIWindow()))))

printf("VLUT ADE plugin loaded (root: %s). CIW menu: VLUT, or type VLUT()\n"
       VLUTRoot)
