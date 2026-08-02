// related-slider.js
document.addEventListener("DOMContentLoaded",()=>{
const scroll=document.querySelector(".related-scroll");
const slider=document.querySelector(".related-slider");
if(!scroll||!slider)return;
[...slider.children].forEach(c=>slider.appendChild(c.cloneNode(true)));
let x=0,auto=true,speed=.4,drag=false,startX=0,startPos=0,v=0,lastX=0,lastT=0,inertia=false;
const limit=()=>slider.scrollWidth/2;
function norm(){const l=limit();while(x>0)x-=l;while(-x>=l)x+=l;}
function frame(){
 if(auto&&!drag&&!inertia){x-=speed;norm();}
 if(inertia){
   x+=v; v*=0.95;
   if(Math.abs(v)<0.1){inertia=false}
 }
 norm();
 slider.style.transform=`translateX(${x}px)`;
 requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
function down(px){
 drag=true;auto=false;inertia=false;startX=px;startPos=x;lastX=px;lastT=performance.now();
}
function move(px){
 if(!drag)return;
 const now=performance.now();
 x=startPos+(px-startX);
 v=(px-lastX)/Math.max(1,(now-lastT))*16;
 lastX=px;lastT=now;
}
function up(){
 if(!drag)return;
 drag=false;inertia=true;
 setTimeout(()=>auto=true,2500);
}
scroll.addEventListener("mousedown",e=>down(e.clientX));
window.addEventListener("mousemove",e=>move(e.clientX));
window.addEventListener("mouseup",up);
scroll.addEventListener("touchstart",e=>down(e.touches[0].clientX),{passive:true});
scroll.addEventListener("touchmove",e=>move(e.touches[0].clientX),{passive:true});
scroll.addEventListener("touchend",up);
});