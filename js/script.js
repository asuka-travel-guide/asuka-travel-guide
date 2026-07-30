/*==========================================
    明日香村観光ガイド
    Hero Slide Show
    script.js Ver2.2
==========================================*/


const slides = [

    {
        image: "images/hero/ishibutai.jpg",
        title: "石舞台古墳",
        link: "spots/ishibutai.html"
    },

    {
        image: "images/hero/inabuchi-tanada.jpg",
        title: "稲渕の棚田",
        link: "spots/inabuchi-tanada.html"
    },

    {
        image: "images/hero/asukadera.jpg",
        title: "飛鳥寺",
        link: "spots/asukadera.html"
    },

    {
        image: "images/hero/okadera.jpg",
        title: "岡寺",
        link: "spots/okadera.html"
    },

    {
        image: "images/hero/kitora.jpg",
        title: "キトラ古墳",
        link: "spots/kitora.html"
    },

    {
        image: "images/hero/kameishi.jpg",
        title: "亀石",
        link: "spots/kameishi.html"
    }

];



const heroImage = document.getElementById("hero-image");

const heroTitle = document.getElementById("hero-title");

const heroLink = document.getElementById("hero-link");



let current = 0;


const fadeTime = 800;



function showSlide(index){


    // 現在画像を消す

    heroImage.style.opacity = 0;



    setTimeout(()=>{


        // 新画像セット

        heroImage.src = slides[index].image;

        heroImage.alt = slides[index].title;

        heroTitle.textContent = slides[index].title;

        heroLink.href = slides[index].link;



        /*
            強制リセット
            ブラウザに変更を認識させる
        */

        heroImage.style.transition = "none";

        heroImage.style.transform = "scale(1)";



        // 再描画

        heroImage.offsetHeight;



        /*
            アニメーション復活
        */

        heroImage.style.transition =
            "opacity .8s ease, transform 8s ease-out";



        // 表示開始

        heroImage.style.opacity = 1;



        // ズーム開始

        setTimeout(()=>{

            heroImage.style.transform = "scale(1.05)";


        },100);



    },fadeTime);


}



function nextSlide(){


    current++;


    if(current >= slides.length){

        current = 0;

    }


    showSlide(current);


}



/*==========================================
    画像先読み
==========================================*/

slides.forEach(slide=>{

    const img = new Image();

    img.src = slide.image;

});



/*==========================================
    初期表示
==========================================*/

showSlide(current);



/*==========================================
    自動再生
==========================================*/

setInterval(nextSlide,6000);