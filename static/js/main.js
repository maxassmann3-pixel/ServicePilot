window.addEventListener("load", function(){
    const splash = document.getElementById("splash");

    if(splash){
        setTimeout(function(){
            splash.style.opacity = "0";

            setTimeout(function(){
                splash.style.display = "none";
            }, 350);

        }, 350);
    }
});

document.querySelectorAll("a").forEach(function(link){
    link.addEventListener("click", function(e){
        const href = link.getAttribute("href");

        if(href && href !== "#" && !href.startsWith("http")){
            e.preventDefault();

            const splash = document.getElementById("splash");

            if(splash){
                splash.style.display = "flex";
                splash.style.opacity = "1";

                setTimeout(function(){
                    window.location.href = href;
                }, 220);
            }else{
                window.location.href = href;
            }
        }
    });
});

function updateTypeFields(){
    const typeSelect = document.getElementById("typeSelect");
    const vehicleFields = document.getElementById("vehicleFields");
    const intervalInput = document.getElementById("intervalInput");

    if(!typeSelect || !vehicleFields || !intervalInput){
        return;
    }

    if(typeSelect.value === "small_device"){
        vehicleFields.style.display = "none";

        if(intervalInput.value === ""){
            intervalInput.value = 500;
        }
    }else{
        vehicleFields.style.display = "block";
    }
}