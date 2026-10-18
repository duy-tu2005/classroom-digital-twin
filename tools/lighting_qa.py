"""Read back the browser-rendered SVG mask; no edits to the approved raster asset."""
def mask_coverage(page, probes=()):
    return page.locator('.cl-lit-scene').evaluate('''async (el,probes)=>{
      const mask=getComputedStyle(el).maskImage;
      if(!mask.startsWith('url('))throw new Error('Illumination mask is missing');
      let url=mask.slice(4,-1);
      if(url[0]==='"'||url[0]==="'")url=url.slice(1,-1);
      const img=new Image();img.src=url;await img.decode();
      const size=512,canvas=document.createElement('canvas');canvas.width=canvas.height=size;
      const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(img,0,0,size,size);
      const data=ctx.getImageData(0,0,size,size).data;
      let minAlpha=255,dimPixels=0;
      for(let i=3;i<data.length;i+=4){minAlpha=Math.min(minAlpha,data[i]);if(data[i]<254)dimPixels++;}
      const probeAlpha=probes.map(([x,y])=>data[(Math.floor(y*size)*size+Math.floor(x*size))*4+3]);
      return {activeLights:el.getAttribute('data-active-lights'),minAlpha,dimPixels,pixels:size*size,probeAlpha};
    }''',list(probes))
