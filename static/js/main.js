// Toggle profile dropdown on small screens
function toggleDropdown() {
    const dropdown = document.getElementById('dropdownContent');
    dropdown.classList.toggle('show');
}

// Close dropdown if clicked outside
window.onclick = function(event) {
    if (!event.target.matches('.profile-circle')) {
        const dropdowns = document.getElementsByClassName('dropdown-content');
        for (let dropdown of dropdowns) {
            if (dropdown.classList.contains('show')) {
                dropdown.classList.remove('show');
            }
        }
    }
}