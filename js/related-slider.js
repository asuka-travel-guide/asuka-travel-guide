document.addEventListener("DOMContentLoaded",()=>{

const scroll=document.querySelector(".related-scroll");
const slider=document.querySelector(".related-slider");

if(!scroll||!slider)return;


/*----------------------------------
複製
----------------------------------*/

[...slider.children].forEach(card=>{
    slider.appendChild(card.cloneNode(true));
});


let x=0;
let auto=true;
const speed=.4;

let startX=0;
let startPos=0;
let dragging=false;

function loop(){

    if(auto){

        x-=speed;

        const limit=slider.scrollWidth/2;

        if(-x>=limit){

            x+=limit;

        }

        slider.style.transform=`translateX(${x}px)`;

    }

    requestAnimationFrame(loop);

}

loop();


/*----------------------------------
PC
----------------------------------*/

scroll.addEventListener("mousedown",e=>{

    dragging=true;
    auto=false;

    startX=e.clientX;
    startPos=x;

    scroll.classList.add("dragging");

});

window.addEventListener("mousemove",e=>{

    if(!dragging)return;

    x=startPos+(e.clientX-startX);

    slider.style.transform=`translateX(${x}px)`;

});

window.addEventListener("mouseup",()=>{

    if(!dragging)return;

    dragging=false;

    scroll.classList.remove("dragging");

    setTimeout(()=>{

        auto=true;

    },1000);

});


/*----------------------------------
スマホ
----------------------------------*/

scroll.addEventListener("touchstart",e=>{

    auto=false;

    startX=e.touches[0].clientX;
    startPos=x;

},{passive:true});


scroll.addEventListener("touchmove",e=>{

    x=startPos+(e.touches[0].clientX-startX);

    slider.style.transform=`translateX(${x}px)`;

},{passive:true});


scroll.addEventListener("touchend",()=>{

    const limit=slider.scrollWidth/2;

    while(x>0){

        x-=limit;

    }

    while(-x>=limit){

        x+=limit;

    }

    setTimeout(()=>{

        auto=true;

    },1000);

});

});