window.addEventListener("load", function(){
    const splash = document.getElementById("splash");

    if(splash){
        setTimeout(function(){
            splash.style.opacity = "0";

            setTimeout(function(){
                splash.style.display = "none";
            }, 300);

        }, 300);
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
                }, 180);
            }else{
                window.location.href = href;
            }
        }
    });
});

function toggleLocationChange(){
    const checkbox = document.getElementById("location_change");
    const box = document.getElementById("location-change-box");

    if(!checkbox || !box){
        return;
    }

    if(checkbox.checked){
        box.style.display = "block";
    }else{
        box.style.display = "none";
    }
}

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