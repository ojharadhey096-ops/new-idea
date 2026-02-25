// Main JavaScript for Video Library

document.addEventListener('DOMContentLoaded', function() {
    // Attach generic form handler only for forms that don't already have an onsubmit handler
    const forms = Array.from(document.querySelectorAll('form'));
    forms.forEach(form => {
        if (form.getAttribute('onsubmit')) return; // skip forms using inline handlers (they handle submission themselves)
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(form);
            fetch('/add_video', {
                method: 'POST',
                body: formData,
                credentials: 'same-origin'
            })
            .then(response => response.json())
            .then(data => {
                alert('Video processing started! It will appear in the folder once downloaded.');
                form.reset();
            })
            .catch(error => {
                alert('Error adding video: ' + error.message);
            });
        });
    });
});