(function(){
  'use strict';

  var pdfModulePromise;
  function loadPdfJs(){
    if(!pdfModulePromise){
      pdfModulePromise=import('/js/pdfjs/pdf.mjs').then(function(pdfjs){
        pdfjs.GlobalWorkerOptions.workerSrc='/js/pdfjs/pdf.worker.mjs';
        return pdfjs;
      });
    }
    return pdfModulePromise;
  }

  function tokens(value){
    return String(value||'').normalize('NFKC').toLocaleLowerCase().match(/[\p{L}\p{N}]+/gu)||[];
  }

  function matchingItemIndexes(items, quote){
    var pageTokens=[];
    items.forEach(function(item,itemIndex){
      tokens(item.str).forEach(function(token){pageTokens.push({token:token,itemIndex:itemIndex});});
    });
    var wanted=tokens(quote);
    if(!wanted.length)return [];
    var start=-1;
    outer:for(var i=0;i<=pageTokens.length-wanted.length;i++){
      for(var j=0;j<wanted.length;j++)if(pageTokens[i+j].token!==wanted[j])continue outer;
      start=i;break;
    }
    if(start<0&&wanted.length>7){
      var anchor=wanted.slice(0,7);
      outer2:for(var k=0;k<=pageTokens.length-anchor.length;k++){
        for(var n=0;n<anchor.length;n++)if(pageTokens[k+n].token!==anchor[n])continue outer2;
        start=k;wanted=anchor;break;
      }
    }
    if(start<0){
      // Tables are often extracted column-by-column by PDF engines, while the
      // stored quote is reconstructed row-by-row. Match complete cell phrases
      // so evidence can still be overlaid on the untouched original table.
      var fallback=[];
      items.forEach(function(item,itemIndex){
        var itemTokens=tokens(item.str);if(!itemTokens.length)return;
        var found=false;
        if(itemTokens.length===1){
          found=itemTokens[0].length>7&&wanted.filter(function(token){return token===itemTokens[0];}).length===1;
        }else{
          cell:for(var i=0;i<=wanted.length-itemTokens.length;i++){
            for(var j=0;j<itemTokens.length;j++)if(wanted[i+j]!==itemTokens[j])continue cell;
            found=true;break;
          }
        }
        if(found)fallback.push(itemIndex);
      });
      return fallback;
    }
    var result=[];
    for(var p=start;p<start+wanted.length;p++){
      var index=pageTokens[p].itemIndex;
      if(result.indexOf(index)<0)result.push(index);
    }
    return result;
  }

  function reveal(container,element){
    if(!element)return;
    var top=element.offsetTop, parent=element.offsetParent;
    while(parent&&parent!==container){top+=parent.offsetTop;parent=parent.offsetParent;}
    container.scrollTo({top:Math.max(0,top-container.clientHeight*.35),behavior:'auto'});
  }

  function mount(container,options){
    if(container._pdfController&&container._pdfController.destroy)container._pdfController.destroy();
    var stopped=false, pageElements={}, pageCanvases={}, pageDrawers={}, evidenceElements={}, pendingPage=1, pendingEvidence=null;
    var observer=null, renderedOrder=[];
    container.innerHTML='<div class="pdf-loading" role="status"><span></span>Rendering original PDF…</div>';
    container.classList.add('original-mode','pdf-original-mode');

    var controller={
      goToPage:function(page){
        pendingPage=Math.max(1,Number(page||1));
        if(pageDrawers[pendingPage])pageDrawers[pendingPage]();
        if(pageElements[pendingPage])reveal(container,pageElements[pendingPage]);
      },
      goToEvidence:function(id){
        pendingEvidence=id;
        var elements=evidenceElements[id];
        if(elements&&elements[0]){
          var page=Number(elements[0].closest('.pdf-page').dataset.page||1);
          if(pageDrawers[page])pageDrawers[page]();
          reveal(container,elements[0]);
        }
      },
      destroy:function(){stopped=true;if(observer)observer.disconnect();},
      ready:null
    };
    container._pdfController=controller;

    controller.ready=loadPdfJs().then(function(pdfjs){
      return pdfjs.getDocument({url:options.url}).promise.then(async function(pdf){
        if(stopped)return;
        container.innerHTML='';
        var evidenceByPage={};
        (options.evidence||[]).forEach(function(item){
          var page=Math.max(1,Number(item.page||1));
          (evidenceByPage[page]||(evidenceByPage[page]=[])).push(item);
        });
        function rememberRendered(pageNumber){
          renderedOrder=renderedOrder.filter(function(value){return value!==pageNumber;});renderedOrder.push(pageNumber);
          while(renderedOrder.length>6){
            var old=renderedOrder.shift(), oldCanvas=pageCanvases[old];
            if(oldCanvas){oldCanvas.width=1;oldCanvas.height=1;oldCanvas.dataset.rendered='false';}
          }
        }
        observer=new IntersectionObserver(function(entries){
          entries.forEach(function(entry){
            if(entry.isIntersecting){var draw=pageDrawers[Number(entry.target.dataset.page)];if(draw)draw();}
          });
        },{root:container,rootMargin:'120% 0px'});
        for(let pageNumber=1;pageNumber<=pdf.numPages;pageNumber++){
          if(stopped)return;
          let page=await pdf.getPage(pageNumber), viewport=page.getViewport({scale:1.6});
          let wrapper=document.createElement('section');
          wrapper.className='pdf-page';wrapper.dataset.page=String(pageNumber);
          wrapper.style.setProperty('--pdf-ratio',viewport.width+'/'+viewport.height);
          wrapper.style.maxWidth=viewport.width+'px';
          let canvas=document.createElement('canvas'), overlay=document.createElement('div'), label=document.createElement('span');
          canvas.setAttribute('aria-label','Original PDF page '+pageNumber);canvas.dataset.rendered='false';
          overlay.className='pdf-highlight-layer';label.className='pdf-page-number';label.textContent='p.'+pageNumber;
          wrapper.appendChild(canvas);wrapper.appendChild(overlay);wrapper.appendChild(label);container.appendChild(wrapper);
          pageElements[pageNumber]=wrapper;pageCanvases[pageNumber]=canvas;
          let rendering=false;
          async function drawPage(){
            if(stopped||rendering||canvas.dataset.rendered==='true')return;
            rendering=true;wrapper.classList.add('rendering');
            var pixelScale=Math.min(2.25,Math.max(2,Number(window.devicePixelRatio||1)));
            var renderViewport=page.getViewport({scale:viewport.scale*pixelScale});
            canvas.width=Math.ceil(renderViewport.width);canvas.height=Math.ceil(renderViewport.height);
            try{
              // PDF pages have a white medium even when the file omits an
              // explicit background. An opaque canvas otherwise starts black,
              // which makes transparent PDFs appear as black pages.
              await page.render({canvasContext:canvas.getContext('2d',{alpha:false}),viewport:renderViewport,background:'#ffffff'}).promise;
              canvas.dataset.rendered='true';rememberRendered(pageNumber);
            }finally{rendering=false;wrapper.classList.remove('rendering');}
          }
          pageDrawers[pageNumber]=drawPage;
          if(pageNumber===1)await drawPage();
          var pageEvidence=evidenceByPage[pageNumber]||[];
          if(pageEvidence.length){
            var text=await page.getTextContent(), styles=text.styles||{}, markersByItem={}, tagsByItem={};
            pageEvidence.forEach(function(evidence){
              var indexes=matchingItemIndexes(text.items,evidence.quote);
              indexes.forEach(function(index){
                var item=text.items[index], tx=pdfjs.Util.transform(viewport.transform,item.transform);
                var fontHeight=Math.hypot(tx[2],tx[3]), style=styles[item.fontName]||{};
                var ascent=style.ascent?style.ascent*fontHeight:(style.descent?(1+style.descent)*fontHeight:fontHeight*.86);
                var width=Math.max(3,Number(item.width||0)*viewport.scale), height=Math.max(3,fontHeight*1.12);
                var marker=markersByItem[index];
                if(!marker){
                  marker=document.createElement('span');marker.className='pdf-ev';markersByItem[index]=marker;
                  marker.style.left=(tx[4]/viewport.width*100)+'%';marker.style.top=((tx[5]-ascent)/viewport.height*100)+'%';
                  marker.style.width=(width/viewport.width*100)+'%';marker.style.height=(height/viewport.height*100)+'%';
                  var angle=Math.atan2(tx[1],tx[0]);if(Math.abs(angle)>.001)marker.style.transform='rotate('+angle+'rad)';
                  overlay.appendChild(marker);
                }
                var markerIds=(marker.dataset.evs||'').split(' ').filter(Boolean);
                if(markerIds.indexOf(evidence.id)<0)markerIds.push(evidence.id);
                marker.dataset.evs=markerIds.join(' ');marker.dataset.ev=markerIds[0];marker.dataset.pdfEv=markerIds[0];
                var markerCriteria=(marker.dataset.criteria||'').split(' ').filter(Boolean), criterionLabel=evidence.criterion_label||'';
                if(criterionLabel&&markerCriteria.indexOf(criterionLabel)<0)markerCriteria.push(criterionLabel);
                marker.dataset.criteria=markerCriteria.join(' ');marker.title='Evidence for '+(markerCriteria.join('/')||evidence.label||'criterion');
                (evidenceElements[evidence.id]||(evidenceElements[evidence.id]=[])).push(marker);
              });
              if(indexes.length){
                var firstIndex=indexes[0], firstMarker=markersByItem[firstIndex], tag=tagsByItem[firstIndex];
                if(!tag){
                  tag=document.createElement('span');tag.className='pdf-ev-tag';tag.style.left=firstMarker.style.left;tag.style.top=firstMarker.style.top;
                  tagsByItem[firstIndex]=tag;overlay.appendChild(tag);
                }
                var tagIds=(tag.dataset.evs||'').split(' ').filter(Boolean), tagCriteria=(tag.dataset.criteria||'').split(' ').filter(Boolean);
                if(tagIds.indexOf(evidence.id)<0)tagIds.push(evidence.id);
                if(evidence.criterion_label&&tagCriteria.indexOf(evidence.criterion_label)<0)tagCriteria.push(evidence.criterion_label);
                tag.dataset.evs=tagIds.join(' ');tag.dataset.criteria=tagCriteria.join(' ');tag.textContent=tagCriteria.join('/');
              }
            });
          }
          if(pendingEvidence&&evidenceElements[pendingEvidence]&&evidenceElements[pendingEvidence][0])reveal(container,evidenceElements[pendingEvidence][0]);
          else if(pendingPage===pageNumber)reveal(container,wrapper);
          await new Promise(function(resolve){setTimeout(resolve,0);});
        }
        Object.keys(pageElements).forEach(function(pageNumber){observer.observe(pageElements[pageNumber]);});
        container.classList.add('pdf-ready');
        return controller;
      });
    }).catch(function(error){
      if(stopped)return;
      container.classList.remove('pdf-original-mode');
      container.innerHTML='<div class="pdf-error"><b>Original PDF could not be rendered.</b><span>'+String(error&&error.message||error)+'</span></div>';
      throw error;
    });
    return controller;
  }

  window.OriginalPdfViewer={mount:mount};
})();
