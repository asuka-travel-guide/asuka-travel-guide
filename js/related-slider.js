document.addEventListener("DOMContentLoaded",()=>{


const slider = document.querySelector(".related-slider");
const scroll = document.querySelector(".related-scroll");


if(!slider || !scroll) return;



/*==========================================
    カード複製
==========================================*/

const cards = [...slider.children];


cards.forEach(card=>{

    const clone = card.cloneNode(true);

    slider.appendChild(clone);

});



/*==========================================
    自動スクロール
==========================================*/

let auto = true;

const speed = 0.4;



function autoSlide(){

    if(auto){

        scroll.scrollLeft += speed;


        /*
          半分進んだら最初へ戻す
          複製済みなので見た目は自然
        */

        if(
            scroll.scrollLeft >=
            slider.scrollWidth / 2
        ){

            scroll.scrollLeft = 0;

        }

    }


    requestAnimationFrame(autoSlide);

}


autoSlide();





/*==========================================
    マウス操作
==========================================*/


scroll.addEventListener("mouseenter",()=>{

    auto=false;

});


scroll.addEventListener("mouseleave",()=>{

    auto=true;

});





/*==========================================
    スマホ操作
==========================================*/


scroll.addEventListener("touchstart",()=>{

    auto=false;

});


scroll.addEventListener("touchend",()=>{

    setTimeout(()=>{

        auto=true;

    },1500);

});



});