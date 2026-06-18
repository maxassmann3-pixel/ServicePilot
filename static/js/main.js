// Kleiner Ladebildschirm: wird bewusst kurz gehalten, damit die App schneller wirkt.
window.addEventListener("load", function(){
    const splash = document.getElementById("splash");

    if(splash){
        setTimeout(function(){
            splash.style.opacity = "0";

            setTimeout(function(){
                splash.style.display = "none";
            }, 160);
        }, 160);
    }

    if(typeof updateTypeFields === "function"){
        updateTypeFields();
    }

    if(typeof showCurrentMachineInfo === "function"){
        showCurrentMachineInfo();
    }
});


// Blendet beim Tagesbericht die Felder für Standortwechsel ein oder aus.
function toggleLocationChange(){
    const checkbox = document.getElementById("location_change");
    const box = document.getElementById("location-change-box");

    if(checkbox && box){
        box.style.display = checkbox.checked ? "block" : "none";
    }
}


// Bei Fahrzeugen werden Kennzeichen und TÜV angezeigt, bei Maschinen nicht zwingend.
function updateTypeFields(){
    const typeSelect = document.getElementById("typeSelect");
    const vehicleFields = document.getElementById("vehicleFields");

    if(!typeSelect || !vehicleFields){
        return;
    }

    vehicleFields.style.display = typeSelect.value === "vehicle" ? "block" : "none";
}