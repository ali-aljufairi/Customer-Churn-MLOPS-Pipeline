const form=document.querySelector('#predict-form');
const state=document.querySelector('#service-state');
fetch('/ready').then(r=>{if(!r.ok)throw Error();state.textContent='Model ready';}).catch(()=>{state.textContent='Model unavailable';state.classList.add('bad');});
fetch('/metadata').then(r=>r.ok?r.json():Promise.reject()).then(m=>{document.querySelector('#model-label').textContent=m.model_name;document.querySelector('#model-detail').textContent=`v${m.model_version} · ROC AUC ${(m.metrics.roc_auc*100).toFixed(1)}%`;}).catch(()=>{document.querySelector('#model-label').textContent='Unavailable';document.querySelector('#model-detail').textContent='Train the model to enable estimates';});

document.querySelectorAll('input[type="number"]').forEach(input=>{
 const wrap=document.createElement('span'); wrap.className='number-control'; input.parentNode.insertBefore(wrap,input); wrap.append(input);
 const makeButton=(label,delta)=>{const button=document.createElement('button');button.type='button';button.className='stepper';button.setAttribute('aria-label',`${label} ${input.name}`);button.textContent=delta<0?'−':'+';button.addEventListener('click',()=>{const step=Number(input.step)||1;const min=input.min===''?-Infinity:Number(input.min);const max=input.max===''?Infinity:Number(input.max);const next=Math.min(max,Math.max(min,Number(input.value||0)+delta*step));input.value=Number.isInteger(step)?next:Number(next.toFixed(2));input.dispatchEvent(new Event('input',{bubbles:true}));});return button;};
 wrap.append(makeButton('Decrease',-1),makeButton('Increase',1));
});
form.addEventListener('submit',async event=>{
 event.preventDefault(); const error=document.querySelector('#error'); error.textContent='';
 if(!form.reportValidity())return;
 const button=document.querySelector('#submit');button.disabled=true;button.textContent='Estimating…';
 const data=Object.fromEntries(new FormData(form));
 for(const [key,value] of Object.entries(data)){if(key==='State'||key.includes('Plan'))continue;data[key]=Number(value);}
 try{
  const response=await fetch('/predict',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result=await response.json(); if(!response.ok){const detail=result.detail;throw Error(typeof detail==='string'?detail:'Please check the highlighted values and try again.');}
  document.querySelector('#empty').hidden=true;document.querySelector('#answer').hidden=false;
  const percent=(result.churn_probability*100).toFixed(1);document.querySelector('#score').innerHTML=`${percent}<small>%</small>`;
  const chip=document.querySelector('#risk-chip');chip.textContent=`${result.risk_level} risk`;chip.className=`chip ${result.risk_level}`;
  document.querySelector('#meter').style.width=`${Math.min(100,result.churn_probability*100)}%`;
  document.querySelector('#classification').textContent=result.churn?`Above the ${Math.round(result.threshold*100)}% model threshold — consider a retention review.`:`Below the ${Math.round(result.threshold*100)}% model threshold — continue monitoring.`;
  const list=document.querySelector('#reasons');list.replaceChildren(...result.explanation.map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
 }catch(e){error.textContent=e.message||'Could not reach the prediction service. Try again.';}
 finally{button.disabled=false;button.innerHTML='Estimate churn risk <span aria-hidden="true">↗</span>';}
});
