window.addEventListener("load", function(){
    const splash = document.getElementById("splash");

    if(splash){
        setTimeout(function(){
            splash.style.opacity = "0";
            setTimeout(function(){
                splash.style.display = "none";
            }, 180);
        }, 180);
    }

    if(typeof updateTypeFields === "function"){
        updateTypeFields();
    }

    if(typeof showCurrentMachineInfo === "function"){
        showCurrentMachineInfo();
    }
});

function toggleLocationChange(){
    const checkbox = document.getElementById("location_change");
    const box = document.getElementById("location-change-box");

    if(checkbox && box){
        box.style.display = checkbox.checked ? "block" : "none";
    }
}

function updateTypeFields(){
    const typeSelect = document.getElementById("typeSelect");
    const vehicleFields = document.getElementById("vehicleFields");

    if(!typeSelect || !vehicleFields){
        return;
    }

    vehicleFields.style.display = typeSelect.value === "vehicle" ? "block" : "none";
}