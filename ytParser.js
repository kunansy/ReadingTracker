const parseDuration = (duration) => {
    let parts = duration.split(":");
    let total = 0;

    switch (parts.length) {
        case 3:
            total += parseInt(parts[0]) * 60;
        case 2:
            total += parseInt(parts[1]);
        case 1:
            total += Math.floor(parseInt(parts[0]) / 60);
        default:
            console.error(`Could not parse duration: ${duration}`);
    }

    return total;
}

const parse = () => {
    let title = document.querySelector("div#title.ytd-watch-metadata yt-formatted-string").textContent;
    let author = document.querySelector("div#owner.ytd-watch-metadata yt-formatted-string").textContent;
    let duration = document.querySelector("div.ytp-time-display span.ytp-time-duration").textContent;
    
    return {
        title: title,
        author: author,
        duration: parseDuration(duration)
    }
}
