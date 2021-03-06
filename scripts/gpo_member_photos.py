#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Scrape http://www.memberguide.gpoaccess.gov and
save members' photos named after their Bioguide IDs.
"""
import argparse
import datetime
import os
import re
import sys
import time
import urllib
import urlparse

# pip install -r requirements.txt
from BeautifulSoup import BeautifulSoup
import mechanize
import yaml


def pause(last, delay):
    if last == None:
        return datetime.datetime.now()

    now = datetime.datetime.now()
    delta = (now - last).total_seconds()

    if delta < delay:
        sleep = delay - delta
        print "Sleep for", int(sleep), "seconds"
        time.sleep(sleep)
    return datetime.datetime.now()

def get_front_page(br, congress_number, delay):
    url = r'http://www.memberguide.gpoaccess.gov/GetMembersSearch.aspx'
    links = []

    ######################################
    # First, open the page to get the form
    ######################################
    br.set_handle_robots(False)   # no robots
    br.set_handle_refresh(False)  # can sometimes hang without this
    br.addheaders = [('User-agent', 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.1) Gecko/2008071615 Fedora/3.0.1-1.fc9 Firefox/3.0.1')]

    print "Open front page:", url
    last_request_time = datetime.datetime.now()
    response = br.open(url).read()

    if len(response) == 0:
        sys.exit("Page is blank. Try again later, you may have hit a limit.")

    # print 'href="' + congress_number in response
    # print response

    ##############################
    # Next, choose congress number
    ##############################
    br.select_form(nr=0)
    br.set_all_readonly(False)      # allow everything to be written to
    form = br.form
    form.set_all_readonly(False)    # allow everything to be written to

    # The only submit button is "Clear Search" and we don't want to do that!
    for control in br.form.controls:
        if control.name == "ctl00$ContentPlaceHolder1$btnClear":
            control.disabled = True
            break

    # The search button is hooked up to a Javascript __doPostBack() function that sets __EVENTTARGET
    br['__EVENTTARGET']='ctl00$ContentPlaceHolder1$btnSearch'

    # Set the congress session number
    br['ctl00$ContentPlaceHolder1$ddlCongressSession']=[congress_number] # Use a list for select controls with multiple values

    print "Submit congress session number:", congress_number
    last_request_time = pause(last_request_time, delay)
    response = br.submit().read()

    # print 'href="' + congress_number in response
    br.select_form(nr=0)
    form = br.form
    # print br['ctl00$ContentPlaceHolder1$ddlCongressSession']

    # TODO: Could change members-per-page so we don't need to keep clicking next

    #############################
    # Choose next page until done
    #############################
    last_page = None
    # Page number:
    this_page = br['ctl00$ContentPlaceHolder1$Memberstelerikrid$ctl00$ctl03$ctl01$GoToPageTextBox']

    while(last_page != this_page):

        # Harvest links
        for link in br.links():
            if congress_number + "/" in link.url:
                if ("/DG/" in link.url or
                    "/SR/" in link.url or
                    "/RC/" in link.url or
                    "/RP/" in link.url):
                    # Include only delegates, a resident commissioner,
                    # representatives and senators.
                    # Exclude capitol, house and senate officials ("CO", "HO", "SO"),
                    # a president ("PR") and a vice-president ("VP") (8 in 113rd)
                    print link.text, link.url
                    links.append(link)
        print "Links:", len(links)

        if args.one_page:
            return links

        br.select_form(nr=0)
        br.set_all_readonly(False)      # allow everything to be written to
        form = br.form
        form.set_all_readonly(False)    # allow everything to be written to

        # The only submit button is "Clear Search" and we don't want to do that!
        for control in br.form.controls:
            if control.name == "ctl00$ContentPlaceHolder1$btnClear":
                control.disabled = True
                break

        # The search button is hooked up to a Javascript __doPostBack() function that sets __EVENTTARGET
        br['__EVENTTARGET']='ctl00$ContentPlaceHolder1$Memberstelerikrid$ctl00$ctl02$ctl00$ctl28'

        print "Submit next page..."
        last_request_time = pause(last_request_time, delay)
        response = br.submit().read()

        # print 'href="' + congress_number in response
        br.select_form(nr=0)
        form = br.form
        # print br['ctl00$ContentPlaceHolder1$ddlCongressSession']

        last_page = this_page
        # Page number:
        this_page = br['ctl00$ContentPlaceHolder1$Memberstelerikrid$ctl00$ctl03$ctl01$GoToPageTextBox']

    ###########################################
    # Done, return links for further processing
    ###########################################
    return links

def load_yaml(filename):
    f = open(filename)
    data = yaml.safe_load(f)
    f.close()
    return data

def remove_from_yaml(data, bioguide_id):
    data[:] = [d for d in data if d['id']['bioguide'] != bioguide_id]
    return data

def get_value(item, key1, key2):
    value = None
    if key2 in item[key1].keys():
        value = item[key1][key2]
    return value

def resolve(data, text):
    if isinstance(text, str):
        text = text.decode('utf-8')

    # hardcoded special cases to deal with bad data in GPO
    if text == "Bradley, Byrne": # Really "Byrne, Bradley"
        return "B001289"
    elif text == "Curson, David Alan": # Really "Curzon, David Alan"
        return "C001089"

    for item in data:
        bioguide = item['id']['bioguide']
        last = item['name']['last']
        first = item['name']['first']
        middle = get_value(item, 'name', 'middle')
        nickname = get_value(item, 'name', 'nickname')
        official = get_value(item, 'name', 'official_full')
        text_reversed = reverse_names(text)
        ballotpedia = get_value(item, 'id', 'ballotpedia')
        wikipedia = get_value(item, 'id', 'wikipedia')

        if text == last + ", " + first:
            return bioguide
        elif middle and text == last + ", " + first + " " + middle:
            return bioguide
        elif official and text_reversed == official:
            return bioguide
        elif nickname and text == last + ", " + nickname:
            return bioguide
        elif middle and text == last + ", " + first + " " + middle[0] + ".":
            return bioguide
        elif text.startswith(last) and ", " + first in text:
            return bioguide
        elif ballotpedia and ballotpedia == text_reversed:
            return bioguide
        elif wikipedia and wikipedia == text_reversed:
            return bioguide

        # Check all of first name, then all letters but last, ..., then first letter
        for i in reversed(range(len(first))):
            if text.startswith(last) and ", " + first[:i+1] in text:
                return bioguide

    return None

def reverse_names(text):
    # Given names like "Hagan, Kay R.", reverse them to "Kay R. Hagan"
    return ' '.join(text.split(',')[::-1]).strip(" ")

# Make sure we have the congress-legislators repository available.
def download_legislator_data():
    # clone it if it's not out
    if not os.path.exists("congress-legislators"):
        print "Cloning the congress-legislators repo..."
        os.system("git clone -q --depth 1 https://github.com/unitedstates/congress-legislators congress-legislators")

    # Update the repo so we have the latest.
    print "Updating the congress-legislators repo..."
    # these two == git pull, but git pull ignores -q on the merge part so is less quiet
    os.system("cd congress-legislators; git fetch -pq; git merge --ff-only -q origin/master")

def bioguide_id_from_url(url):
    bioguide_id = urlparse.parse_qs(urlparse.urlparse(url).query)['index'][0].strip("/")
    bioguide_id = bioguide_id.capitalize()
    return bioguide_id

def bioguide_id_valid(bioguide_id):
    if not bioguide_id:
        return False

    # A letter then six digits
    # For example C001061

    # TODO: Is this specification correct?
    # Assume capital letter because ID finder will have uppercased it
    if re.match(r'[A-Z][0-9][0-9][0-9][0-9][0-9]', bioguide_id):
        return True

    return False


def save_metadata(bioguide_id):
    outdir = "congress/metadata"
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    outfile = os.path.join(outdir, bioguide_id + ".yaml")
    with open(outfile, "w") as f:
        f.write("name: GPO Member Guide\n")
        f.write("link: http://memberguide.gpo.gov\n")


def download_photos(br, member_links, outdir, cachedir, delay):
    last_request_time = None
    print "Found a total of", len(member_links), "member links"
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    if not os.path.exists(cachedir):
        os.makedirs(cachedir)

    todo_resolve = []
    legislators = load_yaml("congress-legislators/legislators-current.yaml")

    for i, member_link in enumerate(member_links):
        print "---"
        print "Processing member", i+1, "of", len(member_links), ":", member_link.text
        bioguide_id = None

        cachefile = os.path.join(cachedir, member_link.url.replace("/", "_") + ".html")
        # print os.path.isfile(cachefile)

        html = ""

        if os.path.isfile(cachefile):
            # Load page from cache
            with open(cachefile, "r") as f:
                html = f.read()

        if len(html) == 0:
            # Open page with mechanize
            last_request_time = pause(last_request_time, delay)
            response = br.follow_link(member_link)
            print response.geturl()
            # print response.read()
            html = response.read()
            if len(html) > 0:
                # Save page to cache
                with open(cachefile, "w") as f:
                    f.write(html)

        soup = BeautifulSoup(html)
        for link in soup.findAll('a'):
            url = link.get('href')
            if "bioguide.congress.gov" in url:
                print url
                bioguide_id = bioguide_id_from_url(url)

                # Validate Bioguide ID
                # One member's link didn't contain the ID: http://young.house.gov
                if not bioguide_id_valid(bioguide_id):
                    bioguide_id = None

                break

        # Resolve Bioguide ID against congress-legislators data
        if not bioguide_id:
            print "Bioguide ID not found in page, resolving"
            bioguide_id = resolve(legislators, member_link.text)

            if not bioguide_id:
                print "Bioguide ID not resolved"
                todo_resolve.append(member_link)

        # Download image
        if bioguide_id:
            print "Bioguide ID:", bioguide_id
            image_tags = soup.findAll('img')

            # TODO: Fine for now as only one image on the page
            for image in image_tags:
                 # TODO: Correct to assume jpg?
                filename = os.path.join(outdir, bioguide_id + ".jpg")
                if os.path.isfile(filename):
                    print "Image already exists:", filename
                elif not args.test:
                    print "Saving image to", filename
                    last_request_time = pause(last_request_time, delay)
                    data = br.open(image['src']).read()
                    br.back()
                    save = open(filename, 'wb')
                    save.write(data)
                    save.close()
                    save_metadata(bioguide_id)
                break

            # Remove this from our YAML list to prevent any bad resolutions later
            legislators = remove_from_yaml(legislators, bioguide_id)

    # TODO: For each entry remaining here, check if they've since left Congress.
    # If not, either need to add a resolving case above, or fix the GPO/YAML data.
    print "---"
    print "Didn't resolve Bioguide IDs:", len(todo_resolve)
    for member_link in todo_resolve:
        print member_link.text, member_link.url


def resize_photos():
    # Assumes they're congress/original/*.jpg
    os.system("scripts/resize-photos.sh")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape http://www.memberguide.gpoaccess.gov and save members' photos named after their Bioguide IDs",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-n', '--congress', default='113',
        help="Congress session number, for example: 110, 111, 112, 113")
    parser.add_argument('-c', '--cache', default='cache',
        help="Directory to cache member pages")
    parser.add_argument('-o', '--outdir', default="congress/original",
        help="Directory to save photos in")
    parser.add_argument('-d', '--delay', type=int, default=5, metavar='seconds',
        help="Rate-limiting delay between scrape requests")
    parser.add_argument('-1', '--one-page', action='store_true',
        help="Only process the first page of results (for testing)")
    parser.add_argument('-t', '--test', action='store_true',
        help="Test mode: don't actually save images")
    args = parser.parse_args()

    # clone or update legislator YAML
    download_legislator_data()

    br = mechanize.Browser()
    member_links = get_front_page(br, args.congress, args.delay)

    download_photos(br, member_links, args.outdir, args.cache, args.delay)

    resize_photos()

# End of file
